"""data/generate_knowledge.py — 阶段 4a 知识库 markdown 一次性生成器。

定位:作者使用的一次性脚本。生成 17 篇行业知识 markdown,落盘到
data/knowledge_base/,供 RAG indexer 切块入向量库。

作者使用,**需要真实 LLM**:DEEPSEEK_API_KEY 或 QWEN_API_KEY。
项目其他模块(indexer / retriever / tests)支持无 key 运行;本脚本是唯一例外。

可重跑性:topic 列表与 prompts 硬编码;LLM 自身随机性由 temperature
控制(client 未暴露 API seed)。失败模式:fail-fast,已生成 markdown 保留现场;
重跑前需手动清空 data/knowledge_base/(否则脚本拒绝运行,防覆盖)。

用法:
    # dry-run:就第 1 个 topic 跑 3 次,打印 prompts + 原始输出 + 多样性对比
    python data/generate_knowledge.py --dry-run

    # 批量:跑全部 17 篇,落盘到 data/knowledge_base/
    python data/generate_knowledge.py
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
import time
from pathlib import Path

# sys.path 引导:data/ 非包,沿用 generate_mock.py 风格,让脚本能 import app.*
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from app.llm.client import get_llm  # noqa: E402

OUT_DIR = _REPO_ROOT / "data" / "knowledge_base"

# 17 篇:7 运营 + 5 归因 + 5 女装。固定顺序、固定 slug、固定 tags = 可重跑。
# (category, slug, title, tags)
TOPICS: list[tuple[str, str, str, list[str]]] = [
    # --- 运营技巧 7 ---
    ("operation", "selection-price-band", "选品思路:主推位与价格带匹配",
     ["选品", "价格带", "人货匹配"]),
    ("operation", "live-script-rhythm", "直播话术节奏:开场—促单—收尾三段式",
     ["话术", "排播"]),
    ("operation", "schedule-day-vs-night", "排播策略:午场与工作日晚场的客群差异",
     ["排播", "学生客群", "职场客群"]),
    ("operation", "hook-vs-profit", "引流款与利润款的搭配逻辑",
     ["选品", "引流", "客单价"]),
    ("operation", "health-metrics", "直播间核心健康度指标:看什么、怎么看",
     ["健康度指标", "GMV", "转化率", "退款率"]),
    ("operation", "newproduct-tempo", "上新节奏:小批量试卖与放量决策",
     ["上新", "选品", "SKU"]),
    ("operation", "paid-vs-organic", "付费投流与自然流量的承接配比",
     ["投流", "流量结构", "ROI"]),
    # --- 归因方法论 5 ---
    ("attribution", "gmv-drop-drilldown", "GMV 异常下跌的归因思路:从流量到转化的逐层下钻",
     ["归因", "GMV", "下钻", "根因"]),
    ("attribution", "conversion-drop-diagnose", "转化率突然下滑的诊断:人货匹配视角",
     ["归因", "转化率", "人货匹配"]),
    ("attribution", "refund-surge", "退款率攀升的归因路径:从 SKU 到品类",
     ["归因", "退款率", "SKU"]),
    ("attribution", "uv-up-gmv-flat", "UV 暴涨但 GMV 没涨:流量结构与人群质量",
     ["归因", "UV", "流量结构"]),
    ("attribution", "sku-anomaly-rootcause", "单品异常的根因排查:从评价/咨询到供应链",
     ["归因", "SKU", "根因"]),
    # --- 女装类目专属 5 ---
    ("category_specific", "spring-window", "春装节奏:春款的上新窗口与下播节点",
     ["春装", "上新", "女装"]),
    ("category_specific", "mid-price-aov", "女装中端价格带(¥100-300)的客单价管理",
     ["价格带", "客单价", "女装"]),
    ("category_specific", "student-vs-young-pro", "学生与职场新人客群的偏好差异",
     ["学生客群", "职场客群", "女装"]),
    # [skipped at stage 4a, hanzi floor conflict]:主题内容空间窄,实跑 hanzi=328 触发 350 下限防御
    ("category_specific", "fabric-risks", "针织、真丝、雪纺面料的质量风险点",
     ["面料", "退款率", "女装"]),
    # [skipped at stage 4a, hanzi floor conflict]:#16 fail-fast 级联未运行;主题同样偏窄,留作 4b 作者手写
    ("category_specific", "basic-vs-trend", "风格选品:基础款 vs 趋势款 的占比经验",
     ["选品", "风格", "女装"]),
]

assert len(TOPICS) == 17, "TOPICS 应为 17 篇(7+5+5)"

_CATEGORY_LABEL = {
    "operation": "直播电商运营技巧",
    "attribution": "异常归因方法论",
    "category_specific": "女装类目专属经验",
}

SYSTEM_PROMPT = """你是直播电商商家"小张女装"的资深运营顾问,正在为商家自己的内部知识库撰写经验文档。

【业务背景】
- 类目:女装(中端,主力价格带 ¥100-300)
- 主播:小张(店主)+ 小李(兼职);主要时段为午场与工作日晚场
- 主力客群:18-24 岁学生 + 25-30 岁职场新人(合计约 85%)
- 当前关注三类典型归因 case:人货错配、流量结构异常、单品质量问题

【角色与立场】
- 你在为同一项目撰写 17 篇知识库文档,不同篇之间立场必须一致、互不矛盾
- 经验语气,写给商家自己看,不要写得像营销稿或教科书

【写作硬约束】
- 长度严格控制在 400-600 汉字之间。这是硬约束,不是建议
- 超过 650 字视为不合格,你必须主动收敛删减,宁短勿长
- 错误示范:堆砌"黄金30秒/憋单位/核心停留位"这类术语清单
- 正确示范:每个观点用 1-2 句话讲透,不展开子要点
- 写完后心里默数一遍字数,超过 600 字必须删减再输出
- 正文首行写"适用场景:<一句话>"声明本篇适用的具体场景,空一行后接 `## 二级标题` 分节
- 全文 2 个 ## 二级标题(不是 3 个,不要为凑字数硬加第 3 节)
- 每个 ## 节正文严格控制在 120-180 汉字(注意:汉字,不含标点数字)
- 严禁 ### 三级标题、严禁多层 bullet 嵌套
- bullet 最多 3 条,每条 1 行
- 不要输出一级 `#` 标题(标题由系统拼接)
- 不要输出 front-matter / yaml / ``` 包裹;直接输出 markdown 正文
- 严禁出现任何具体百分比、ROI、转化率、退款率等数字,无论用于基线声明、案例叙述、还是举例对比
- 涉及数据时一律用相对表述:"明显低于历史基线"、"翻了数倍"、"显著高于行业平均"、"几乎可以忽略"
- 用简洁中文写作,可读性优先于学术性"""

USER_PROMPT_TPL = """请就以下主题撰写一篇知识库文档:

主题:{title}
类别:{category_label}

按系统提示中的写作硬约束输出 markdown 正文。"""


# 剥外层 ```...``` 包裹:LLM 偶尔会用 ```markdown\n...\n``` 包响应。
# 锚定 $ 让非贪婪 *? 最终匹配「文档末尾的那条 ```」,避免误剥内嵌代码块的内层 fence。
_FENCE_RE = re.compile(r"^```(?:[\w-]+)?\s*\n([\s\S]*?)\n```\s*$")


def _strip_fence(text: str) -> str:
    """剥外层 ``` 代码块包裹;无包裹原样返回。"""
    t = text.strip()
    m = _FENCE_RE.match(t)
    return m.group(1).strip() if m else t


# 批量阶段硬兜底:汉字数边界 + D 约束 grep。任一失败 fail-fast,不重试、不近似。
_HANZI_FLOOR, _HANZI_CEIL = 350, 700
_RE_DIGIT_PERCENT = re.compile(r"\d+(?:\.\d+)?\s*%")
_RE_DIGIT_TIMES = re.compile(r"(?<!\d)\d+(?:\.\d+)?\s*倍")


def _count_hanzi(text: str) -> int:
    """汉字数 = 落在 CJK 统一表意区(U+4E00–U+9FFF)的字符数;不含标点/数字/ASCII。"""
    return sum(1 for c in text if "一" <= c <= "鿿")


def _validate_body(body: str) -> None:
    """批量阶段双兜底:汉字字数 + D 约束 grep。任一不通过抛 ValueError。"""
    hanzi = _count_hanzi(body)
    if not (_HANZI_FLOOR <= hanzi <= _HANZI_CEIL):
        raise ValueError(
            f"hanzi 失控:{hanzi} 字(要求 {_HANZI_FLOOR}-{_HANZI_CEIL})"
        )
    pcts = _RE_DIGIT_PERCENT.findall(body)
    times = _RE_DIGIT_TIMES.findall(body)
    if pcts or times:
        hits = []
        if pcts:
            hits.append(f"百分比={pcts}")
        if times:
            hits.append(f"具体倍数={times}")
        raise ValueError("D 约束违规,命中:" + " ".join(hits))


def _require_llm():
    """入口防御:无 key (LocalStub) 时显式 fail-fast,文案对 clone 项目的人友好。"""
    llm = get_llm()
    if getattr(llm, "is_stub", False):
        raise RuntimeError(
            "generate_knowledge.py 需要真实 LLM,请配置 DEEPSEEK_API_KEY "
            "或 QWEN_API_KEY 后重试。\n"
            "(本项目其他模块支持无 key 运行,但知识库生成是作者一次性任务,"
            "依赖真实 LLM 输出。)"
        )
    return llm


def _build_front_matter(title: str, category: str, tags: list[str],
                        generated_by: str) -> str:
    today = dt.date.today().isoformat()
    tags_inline = ", ".join(tags)
    return (
        "---\n"
        f"title: {title}\n"
        f"category: {category}\n"
        f"tags: [{tags_inline}]\n"
        f"generated_at: {today}\n"
        f"generated_by: {generated_by}\n"
        "---\n\n"
    )


def _generate_body(llm, title: str, category: str) -> str:
    """调一次 LLM 返回原始响应文本(不剥 fence)。失败上抛由调用方 fail-fast。"""
    user_prompt = USER_PROMPT_TPL.format(
        title=title, category_label=_CATEGORY_LABEL[category]
    )
    return llm.chat(
        system=SYSTEM_PROMPT,
        user=user_prompt,
        temperature=0.7,
        timeout=60.0,
    )


def _diversity_preview(samples: list[str]) -> str:
    """多样性概览:字数 / ## 二级标题数 / 首行预览。"""
    lines = []
    for i, s in enumerate(samples, 1):
        body = _strip_fence(s)
        char_count = len(body)
        h2_count = len(re.findall(r"^##\s", body, flags=re.M))
        first_line = body.splitlines()[0] if body else "(空)"
        first_line_short = first_line[:60] + ("…" if len(first_line) > 60 else "")
        lines.append(
            f"  [{i}] {char_count} 字 / {h2_count} 个 ## / 首行:{first_line_short}"
        )
    return "\n".join(lines)


def cmd_dry_run() -> None:
    """就第 1 个 topic 跑 3 次,打印 prompts、3 次原始输出、多样性概览(不落盘)。"""
    llm = _require_llm()
    category, slug, title, tags = TOPICS[0]
    user_prompt = USER_PROMPT_TPL.format(
        title=title, category_label=_CATEGORY_LABEL[category]
    )

    print("=" * 72)
    print(f"DRY RUN — provider={llm.provider}  model={llm.model}  temperature=0.7")
    print(f"dry-run topic: [{category}] {title}")
    print("=" * 72)
    print("\n--- SYSTEM PROMPT ---\n")
    print(SYSTEM_PROMPT)
    print("\n--- USER PROMPT ---\n")
    print(user_prompt)

    samples: list[str] = []
    for i in range(1, 4):
        print(f"\n--- RAW OUTPUT [{i}/3] ---\n")
        t0 = time.time()
        raw = _generate_body(llm, title, category)
        elapsed = time.time() - t0
        print(raw)
        print(f"\n(elapsed {elapsed:.1f}s, raw_len={len(raw)})")
        samples.append(raw)

    print("\n--- DIVERSITY PREVIEW (post strip-fence) ---")
    print(_diversity_preview(samples))
    print("\nDRY RUN 完成。请人工 review prompts / 内容质量 / 多样性,")
    print("确认后再去掉 --dry-run 跑批量。")


def cmd_batch() -> None:
    """批量生成 17 篇落盘。已存在 markdown 时拒绝运行,防覆盖。"""
    llm = _require_llm()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    existing = sorted(OUT_DIR.glob("*.md"))
    if existing:
        raise RuntimeError(
            f"data/knowledge_base/ 已有 {len(existing)} 篇 markdown,拒绝批量运行(防覆盖)。\n"
            "请人工清空后重试:rm data/knowledge_base/*.md"
        )

    print(f"批量生成 {len(TOPICS)} 篇 → {OUT_DIR.relative_to(_REPO_ROOT)}/")
    print(f"provider={llm.provider}  model={llm.model}  temperature=0.7\n")

    for i, (category, slug, title, tags) in enumerate(TOPICS, 1):
        out_path = OUT_DIR / f"{category}-{slug}.md"
        t0 = time.time()
        try:
            raw = _generate_body(llm, title, category)
            body = _strip_fence(raw)
            _validate_body(body)  # 双兜底:汉字 + D grep,失败即 fail-fast
        except Exception as e:
            print(f"[{i:02d}/{len(TOPICS)}] ✗ {category}/{slug} 失败:{e}")
            print(f"已生成 {i - 1}/{len(TOPICS)} 篇,fail-fast 终止,现场保留。")
            raise
        front_matter = _build_front_matter(title, category, tags, llm.model)
        out_path.write_text(front_matter + body + "\n", encoding="utf-8")
        elapsed = time.time() - t0
        hz = _count_hanzi(body)
        print(f"[{i:02d}/{len(TOPICS)}] ✓ {category}/{slug}  "
              f"({hz} 汉字, {elapsed:.1f}s)")

    print(f"\n全部 {len(TOPICS)} 篇生成完成 → {OUT_DIR.relative_to(_REPO_ROOT)}/")


def cmd_verify() -> None:
    """对 data/knowledge_base/*.md 复用批量阶段的 4 项 check;生成后/审稿期可重复跑。"""
    files = sorted(OUT_DIR.glob("*.md"))
    if not files:
        raise RuntimeError(
            f"{OUT_DIR.relative_to(_REPO_ROOT)}/ 为空,无可验证文件"
        )

    print(f"verify {len(files)} 篇 → {OUT_DIR.relative_to(_REPO_ROOT)}/")
    print(f"{'#':<3}{'file':<48}{'hanzi':<8}{'##':<4}{'D 命中':<22}{'pass':<5}")
    print("-" * 90)
    fm_re = re.compile(r"^---\n.*?\n---\n\n?(.*)$", re.DOTALL)
    all_pass = True
    for i, p in enumerate(files, 1):
        text = p.read_text(encoding="utf-8")
        m = fm_re.match(text)
        body = m.group(1) if m else text
        hz = _count_hanzi(body)
        h2 = len(re.findall(r"^##\s", body, flags=re.M))
        pcts = _RE_DIGIT_PERCENT.findall(body)
        times = _RE_DIGIT_TIMES.findall(body)
        hanzi_ok = _HANZI_FLOOR <= hz <= _HANZI_CEIL
        h2_ok = (h2 == 2)
        d_ok = not pcts and not times
        ok = hanzi_ok and h2_ok and d_ok
        if not ok:
            all_pass = False
        d_hit = "(无)" if d_ok else f"%={pcts} 倍={times}"
        print(f"{i:<3}{p.name:<48}{hz:<8}{h2:<4}{d_hit:<22}{'✓' if ok else '✗':<5}")

    print()
    if all_pass:
        print(f"汇总:{len(files)}/{len(files)} 全部 4 项 check 通过 ✓")
    else:
        print(f"汇总:存在不通过文件,请按行检查 ✗")
        raise SystemExit(1)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="阶段 4a 知识库 markdown 生成器")
    g = p.add_mutually_exclusive_group()
    g.add_argument(
        "--dry-run", action="store_true",
        help="只跑第 1 个 topic 3 次,打印 prompts + 输出 + 多样性,不落盘",
    )
    g.add_argument(
        "--verify", action="store_true",
        help="不调 LLM;对 data/knowledge_base/*.md 跑同样 4 项 check",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    if args.dry_run:
        cmd_dry_run()
    elif args.verify:
        cmd_verify()
    else:
        cmd_batch()
