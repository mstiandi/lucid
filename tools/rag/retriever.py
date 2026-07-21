"""
理论检索：输入 pending claims → 拼接 query → 语义检索 → 格式化为 prompt 可注入文本。
"""

from tools.rag.theory_store import TheoryStore

# 模块级单例，import 时（主线程）即初始化，避免在 LangGraph 线程池中首次加载模型
_store: TheoryStore | None = None


def _get_store() -> TheoryStore:
    global _store
    if _store is None:
        _store = TheoryStore()
        _store.ensure_indexed()
    return _store


# 在 import 时初始化，确保在主线程完成
_get_store()


def retrieve_theories_raw(claims: list[dict], top_k: int = 3) -> list[dict]:
    """
    同 retrieve_theories 但不格式化——返回原始卡片 dict 列表，用于评估召回率。
    """
    if not claims:
        return []

    query = " ".join([c.get("content", "") for c in claims if c.get("content", "")])
    if not query.strip():
        return []

    store = _get_store()
    return store.search(query, top_k=top_k)


def retrieve_theories(claims: list[dict], top_k: int = 3) -> str:
    """
    输入 pending claims → 检索 top_k 理论卡片 → 返回格式化的 prompt 文本。

    Args:
        claims: pending claims 列表，每个 dict 必须有 "content" 字段
        top_k: 检索数量

    Returns:
        格式化的理论参考文本，可直接注入 prompt。
        如果没有 claims 或检索结果为空，返回空字符串。
    """
    if not claims:
        return ""

    # 拼接所有 claim content 为 query
    query = " ".join([c.get("content", "") for c in claims if c.get("content", "")])
    if not query.strip():
        return ""

    store = _get_store()
    cards = store.search(query, top_k=top_k)

    if not cards:
        return ""

    return _format_cards(cards)


def _format_cards(cards: list[dict]) -> str:
    """将卡片列表格式化为 prompt 可注入的文本块。"""
    lines = [
        "## 心理学理论工具（不是参考——你必须使用）\n",
        "以下是通过语义检索匹配到的心理学理论。在你的分析中，你必须：\n",
        "- 至少引用一条理论来解释用户认知偏差的机制\n",
        "- 用理论名称明确标注你用的是哪条理论（如：这是典型的基本归因错误）\n",
        "- 不只是在分析末尾贴一个理论名字——要把理论的核心逻辑应用到对用户具体场景的解释中\n",
    ]
    for i, card in enumerate(cards, 1):
        name = card.get("name", "?")
        category = card.get("category", "")
        core = card.get("core_idea", "")
        signals = card.get("signals_to_look_for", "")
        misinterpret = card.get("common_misinterpretations", "")

        header = f"**{name}**"
        if category:
            header += f"（{category}）"

        lines.append(f"### {i}. {header}")
        lines.append(f"核心：{core}")
        if signals:
            lines.append(f"观察点：{signals}")
        if misinterpret:
            lines.append(f"常见误判：{misinterpret}")
        lines.append("")  # 空行分隔

    return "\n".join(lines)
