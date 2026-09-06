"""
压缩节点：在 supervisor 之后、三个分析节点之前，对 all_signals.behaviors 做状态层有界化。

纯节点：不碰 store。fact 已在 signals_node（出生时）写入，这里只压缩 state 里最老的行为，
防止 behaviors 无限增长导致 MemorySaver checkpoint 内存膨胀。

触发条件：user + ta 的 behaviors 总数 > MAX_BEHAVIORS。
"""
from ..state.JokerState import JokerState
from tools.context.compressor import compress_behaviors
from tools.logger import get_logger

MAX_BEHAVIORS = 200   # behaviors 总数上限（user + ta）
KEEP_RECENT = 50      # 压缩时保留最近条数


def compression_node(state: JokerState) -> dict:
    all_signals = state.get("all_signals")
    if not all_signals:
        return {}

    total = len(all_signals.get("user", {}).get("behaviors", [])) + \
            len(all_signals.get("ta", {}).get("behaviors", []))
    if total <= MAX_BEHAVIORS:
        return {}

    log = get_logger()
    compressed = {
        "user": dict(all_signals.get("user", {})),
        "ta": dict(all_signals.get("ta", {})),
    }
    for person in ["user", "ta"]:
        behaviors = all_signals.get(person, {}).get("behaviors", [])
        label = "用户" if person == "user" else "对方"
        compressed_behaviors, removed = compress_behaviors(behaviors, keep_recent=KEEP_RECENT, label=label)
        compressed[person]["behaviors"] = compressed_behaviors
        if removed:
            log.info("COMPRESSION", f"{person} 压缩 {len(removed)} 条旧行为")

    return {"all_signals": compressed}
