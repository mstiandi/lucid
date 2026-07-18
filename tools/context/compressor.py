"""
压缩all_signals.behaviors的函数，供prompt_builder.build_prompt()调用。用于evidence/alternative/info_symmetry节点的token预算控制。
"""
from collections import Counter


def compress_signals(all_signals: dict, keep_recent: int = 5) -> dict:
    """
    压缩all_signals.behaviors，保留最近的keep_recent条行为，其余按signal_type分组统计摘要。
    Args:
        all_signals (dict): JokerState中的all_signals字段
        keep_recent (int): 保留最近的行为条数
    Returns:
        dict: 与all_signals同结构，但不修改输入
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
        behaviors = all_signals[person].get("behaviors", [])
        if len(behaviors) <= keep_recent:
            compressed[person]["behaviors"] = list(behaviors)
            continue

        # keep_recent=0 → 全部行为作为"老行为"压缩，不保留原始行为
        recent = behaviors[-keep_recent:] if keep_recent > 0 else []
        old = behaviors[:-keep_recent] if keep_recent > 0 else list(behaviors)

        if not old:
            compressed[person]["behaviors"] = list(behaviors)
            continue

        # 按 signal_type 分组：统计数量、confidence列表、action列表
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

        # 每个 type 一行：数量 + 平均confidence + 高频action举例
        lines = []
        for st, info in sorted_groups:
            avg_c = round(sum(info["confidences"]) / len(info["confidences"]), 2)
            top_actions = Counter(info["actions"]).most_common(3)
            action_str = "、".join(f"{a}({n}次)" for a, n in top_actions)
            lines.append(f"{st}({info['count']}条, avg {avg_c}): {action_str}")

        person_label = "用户" if person == "user" else "对方"
        summary_text = f"【历史行为摘要-{person_label}】共{total_count}条（avg {total_avg}）。" + "；".join(lines)

        # 摘要作为一条 behavior 插入最前，后面跟最新的 keep_recent 条
        compressed[person]["behaviors"].append({
            "action": "历史行为摘要",
            "signal_type": "summary",
            "confidence": total_avg,
            "source_ref": summary_text,
        })
        compressed[person]["behaviors"].extend(recent)

    return compressed
