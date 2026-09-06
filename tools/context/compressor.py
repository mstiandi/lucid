"""
压缩 all_signals.behaviors 的工具函数，供两个入口复用：
1. compression_node（状态层）：有界化 state 里的 behaviors，防止 checkpoint 内存无限增长
2. prompt_builder（prompt 层）：token 兜底，压缩 prompt 里的 all_signals 副本

核心函数 compress_behaviors 返回 (压缩后的 behaviors, 被移除的老 behaviors)。
"被移除的"在状态层由 fact 机制兜底（signals_node 出生时已写 fact），
在 prompt 层直接丢弃（只是临时副本，不影响 state）。
"""
from collections import Counter


def compress_behaviors(behaviors: list[dict], keep_recent: int = 5, label: str = "") -> tuple[list, list]:
    """
    压缩单人的 behaviors 列表：保留最近 keep_recent 条，其余按 signal_type 分组统计摘要。

    Args:
        behaviors: 单人的 behaviors 列表
        keep_recent: 保留最近的行为条数
        label: 摘要前缀的人称标签（"用户"/"对方"）

    Returns:
        (compressed_behaviors, removed_behaviors)
        - compressed: [摘要 behavior] + 最近 keep_recent 条
        - removed: 被压缩掉的老 behaviors（供 fact 化或日志）
    """
    if len(behaviors) <= keep_recent:
        return list(behaviors), []

    # keep_recent=0 → 全部行为作为"老行为"压缩，不保留原始行为
    recent = behaviors[-keep_recent:] if keep_recent > 0 else []
    old = behaviors[:-keep_recent] if keep_recent > 0 else list(behaviors)

    if not old:
        return list(behaviors), []

    # 按 signal_type 分组：统计数量、confidence 列表、action 列表
    groups: dict[str, dict] = {}
    for b in old:
        st = b.get("signal_type", "未分类")
        if st not in groups:
            groups[st] = {"count": 0, "confidences": [], "actions": []}
        groups[st]["count"] += 1
        groups[st]["confidences"].append(b.get("confidence", 0.5))
        groups[st]["actions"].append(b.get("action", "?"))

    # 总体统计
    total_count = len(old)
    total_confidences = [c for st, info in groups.items() for c in info["confidences"]]
    total_avg = round(sum(total_confidences) / len(total_confidences), 2)

    # 按数量从多到少排序
    sorted_groups = sorted(groups.items(), key=lambda x: x[1]["count"], reverse=True)

    # 每个 type 一行：数量 + 平均 confidence + 高频 action 举例
    lines = []
    for st, info in sorted_groups:
        avg_c = round(sum(info["confidences"]) / len(info["confidences"]), 2)
        top_actions = Counter(info["actions"]).most_common(3)
        action_str = "、".join(f"{a}({n}次)" for a, n in top_actions)
        lines.append(f"{st}({info['count']}条, avg {avg_c}): {action_str}")

    prefix = f"【历史行为摘要-{label}】" if label else "【历史行为摘要】"
    summary_text = f"{prefix}共{total_count}条（avg {total_avg}）。" + "；".join(lines)

    # 摘要作为一条 behavior 插入最前，后面跟最新的 keep_recent 条
    summary_behavior = {
        "action": "历史行为摘要",
        "signal_type": "summary",
        "confidence": total_avg,
        "source_ref": summary_text,
    }

    return [summary_behavior] + recent, old


def compress_signals(all_signals: dict, keep_recent: int = 5) -> dict:
    """
    压缩 all_signals.behaviors（prompt 层入口），返回与 all_signals 同结构的新 dict，不修改输入。
    """
    if not all_signals:
        return all_signals

    compressed = {
        "user": {
            "initiative_score": all_signals.get("user", {}).get("initiative_score", 0.0),
            "emotional_explicitness": all_signals.get("user", {}).get("emotional_explicitness", 0.0),
            "signal_clarity": all_signals.get("user", {}).get("signal_clarity", 0.0),
            "behaviors": [],
        },
        "ta": {
            "initiative_score": all_signals.get("ta", {}).get("initiative_score", 0.0),
            "emotional_explicitness": all_signals.get("ta", {}).get("emotional_explicitness", 0.0),
            "signal_clarity": all_signals.get("ta", {}).get("signal_clarity", 0.0),
            "behaviors": [],
        },
    }

    for person in ["user", "ta"]:
        behaviors = all_signals.get(person, {}).get("behaviors", [])
        label = "用户" if person == "user" else "对方"
        compressed_behaviors, _ = compress_behaviors(behaviors, keep_recent=keep_recent, label=label)
        compressed[person]["behaviors"] = compressed_behaviors

    return compressed
