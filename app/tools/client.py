"""MCP Client:把异步 MCP stdio 协议桥接成同步 call_tool,供节点薄壳调用。

为什么是这套结构(面试可讲点):
- MCP 官方 SDK 全异步(stdio_client / ClientSession 是 async ctx manager),
  而本仓库节点 / graph.invoke / chat.py / test_graph 全同步且不能改
  → 异步必须藏在同步壳后面。
- 模块级懒加载单例:节点 import call_tool 直接用,不污染 LangGraph state
  (state 不能装活的子进程句柄),test_graph 裸 dict invoke 一行不改。
- 单个常驻后台事件循环线程 + 长生命周期 ClientSession + 单个 Server 子进程:
  全程只起一次子进程(S2),而非每次调用重启(S1 每次 0.5-1s 会卡演示)。
- fail-fast:子进程起不来/超时/tool 报错 → 抛 MCPClientError 让上层看见,
  绝不返回伪造数字;不做自动重试/熔断/健康检查(非演示价值)。
"""
from __future__ import annotations

import asyncio
import atexit
import json
import sys
import threading
from concurrent.futures import TimeoutError as FuturesTimeout
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_STARTUP_TIMEOUT = 20  # 子进程起 + DuckDB import
_CALL_TIMEOUT = 30     # 单次 tool(纯本地 DuckDB 查询,远用不到)


class MCPClientError(RuntimeError):
    """MCP 调用失败。带排查提示,不被 swallow,上抛到 chat.py / test_graph。"""


class _MCPClient:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._session: ClientSession | None = None
        self._thread: threading.Thread | None = None
        self._shutdown: asyncio.Event | None = None
        self._ready = threading.Event()
        self._err: BaseException | None = None
        self._lock = threading.Lock()

    # ---- 懒启动:首次调用才拉起子进程(strategy/Router-only 查询零开销)----
    def _ensure_started(self) -> None:
        with self._lock:
            if self._session is not None:
                return
            if self._err is not None:
                raise self._err  # 已失败过:fail-fast,不自动重试
            self._thread = threading.Thread(
                target=self._run, name="mcp-client-loop", daemon=True
            )
            self._thread.start()
            if not self._ready.wait(timeout=_STARTUP_TIMEOUT):
                self._err = MCPClientError(
                    f"MCP Server 启动超时(>{_STARTUP_TIMEOUT}s)。"
                    f"排查:确认 `{sys.executable} -m app.tools.server` 能在 "
                    f"{_PROJECT_ROOT} 下独立运行(stdio 阻塞等输入属正常)。"
                )
                raise self._err
            if self._err is not None:
                raise self._err

    def _run(self) -> None:
        try:
            asyncio.run(self._serve())
        except BaseException as e:  # 子进程/会话建立失败 → 记录并放行等待方
            self._err = e
            self._ready.set()

    async def _serve(self) -> None:
        """单一长生命周期协程:开 ctx → 就绪 → 等关闭信号 → 同任务退出 ctx。

        进出 anyio ctx 必须在同一 task,故用一个协程贯穿整个生命周期。
        """
        self._loop = asyncio.get_running_loop()
        self._shutdown = asyncio.Event()
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "app.tools.server"],
            cwd=str(_PROJECT_ROOT),
        )
        try:
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    self._session = session
                    self._ready.set()
                    await self._shutdown.wait()
        except BaseException as e:
            self._err = e
            self._ready.set()

    def call_tool(self, name: str, **arguments) -> dict:
        """同步调用 MCP tool,返回 {task,headline,data,evidence} 契约 dict。"""
        self._ensure_started()
        assert self._session is not None and self._loop is not None
        # None 参数不下发(让 Server 走默认窗口,而非传 null 触发 schema 校验)
        args = {k: v for k, v in arguments.items() if v is not None}
        fut = asyncio.run_coroutine_threadsafe(
            self._session.call_tool(name, args), self._loop
        )
        try:
            resp = fut.result(timeout=_CALL_TIMEOUT)
        except FuturesTimeout as e:
            raise MCPClientError(
                f"tool `{name}` 调用超时(>{_CALL_TIMEOUT}s)。"
                f"排查:单独跑 `{sys.executable} -m app.tools.server` 看是否卡死。"
            ) from e

        if resp.isError:
            detail = resp.content[0].text if resp.content else "(无错误内容)"
            raise MCPClientError(f"tool `{name}` 执行出错: {detail}")
        if not resp.content:
            raise MCPClientError(f"tool `{name}` 返回空内容")
        return json.loads(resp.content[0].text)

    def close(self) -> None:
        if self._loop and self._shutdown and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._shutdown.set)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)


_CLIENT = _MCPClient()
atexit.register(_CLIENT.close)


def call_tool(name: str, **arguments) -> dict:
    """模块级入口:节点 `from app.tools.client import call_tool` 直接用。"""
    return _CLIENT.call_tool(name, **arguments)
