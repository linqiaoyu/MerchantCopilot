"""CLI 入口(阶段 2:一次性 query 模式)。

    python scripts/chat.py "2026-04-02 GMV 为什么暴跌"

跑完打印 Steps(执行轨迹)+ Answer(最终回答)后退出。
不做 REPL / 对话历史(对话记忆属阶段 4 Memory 范畴)。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.graph import build_graph  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        print('用法: python scripts/chat.py "你的问题"')
        sys.exit(1)

    query = sys.argv[1]
    state = build_graph().invoke({"user_query": query})

    print("=" * 10, "Steps", "=" * 10)
    for s in state.get("steps", []):
        print(f'[{s["node"]}] {s["summary"]}')

    nr = state.get("node_result") or {}
    if nr:
        print()
        print(f'  task     = {nr.get("task")}')
        print(f'  data     = '
              f'{json.dumps(nr.get("data", {}), ensure_ascii=False, default=str)}')
        for e in nr.get("evidence", []):
            print(f"  evidence - {e}")

    print()
    print("=" * 10, "Answer", "=" * 10)
    print(state.get("final_answer", ""))


if __name__ == "__main__":
    main()
