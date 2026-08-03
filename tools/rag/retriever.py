"""
理论检索：输入 pending claims → 拼接 query → 语义检索 → 格式化为 prompt 可注入文本。

当 sentence_transformers 不可用时（如轻量部署），降级为空返回。
"""

# 模块级单例，import 时（主线程）即初始化，避免在 LangGraph 线程池中首次加载模型
_store: "TheoryStore | None" = None
_rag_available: bool | None = None  # None=未检测, True/False=已检测


def _check_rag() -> bool:
    """检测 RAG 是否可用，只检测一次。"""
    global _rag_available
    if _rag_available is None:
        try:
            from tools.rag.theory_store import TheoryStore
            _rag_available = True
        except ImportError:
            _rag_available = False
    return _rag_available


def _get_store() -> "TheoryStore | None":
    global _store
    if not _check_rag():
        return None
    if _store is None:
        from tools.rag.theory_store import TheoryStore
        _store = TheoryStore()
        _store.ensure_indexed()
    return _store


# 在 import 时尝试初始化，确保在主线程完成；失败则降级
try:
    _get_store()
except Exception:
    _rag_available = False


def retrieve_theories_raw(claims: list[dict], top_k: int = 3) -> list[dict]:
    """
    同 retrieve_theories 但不格式化——返回原始卡片 dict 列表，用于评估召回率。
    RAG 不可用时返回空列表。
    """
    if not claims:
        return []

    store = _get_store()
    if store is None:
        return []

    query = " ".join([c.get("content", "") for c in claims if c.get("content", "")])
    if not query.strip():
        return []

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
    if store is None:
        return ""

    cards = store.search(query, top_k=top_k)

    if not cards:
        return ""

    return _format_cards(cards)


def _format_cards(cards: list[dict]) -> str:
    """将卡片列表格式化为 prompt 可注入的文本块。"""
    lines = [
        "## 心理学理论工具（不是参考——你必须使用）\n",
        "以下是通过语义检索匹配到的心理学理论。在开始分析之前，你必须：\n",
        "1. 逐条判断这条理论的核心机制在用户场景中有没有对应的具体表现（不是\"有点相关\"——是机制是否被明确演示）\n",
        "2. 精确匹配 > 宽泛相关：如果某条理论描述的机制被用户场景明确演示（如\"因为上次被伤所以怕这次也会\"→可得性启发），该理论优先级最高\n",
        "3. 不要被情绪词带偏：用户表达了焦虑/伤心≠需要用依恋理论。先看认知机制（用户怎么想的），再看情绪内容（用户感受到了什么）\n",
        "4. 特异性优先：命名了具体认知机制的理论（可得性启发、基本归因错误、投射效应）优先于适用范围过宽的理论（认知失调、情绪推理）\n",
        "5. 用理论名称明确标注（如\"这是典型的可得性启发\"），并把理论逻辑落实到对用户具体场景的解释中\n",
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
