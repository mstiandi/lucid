"""
对应JokerState中的all_signals字段的reducer，处理信号的合并和更新。
"""

# 首先确定all_signals的结构:
# {"user": {"initiative_score": float, "emotional_explicitness": float, "signal_clarity": float, "behaviors": list[SignalBehavior]},
#  "ta": {"initiative_score": float, "emotional_explicitness": float, "signal_clarity": float, "behaviors": list[SignalBehavior]}}

# SignalBehavior = {
#     "action": str,
#     "signal_type": str,
#     "confidence": float,
#     "source_ref": str  # 原话
# }

# 每次主要更新的就是behaviors列表，其他的用signal_agent进行初始聊天记录判定，
# 然后每次new_signals经过signals_agent，再判定是否需要更新前三个参数，
# 主要取决于behaviors是否不太符合前三者的既有值

def all_signals_reducer(old_signals: dict | None, new_signals: dict | None) -> dict:
    """
    合并旧的信号和新的信号，返回更新后的all_signals。
    Args:
        old_signals (dict | None): 旧的信号字典，可能为None。
        new_signals (dict | None): 新的信号字典，可能为None。
    """
    # 处理None的情况
    if old_signals is None:
        old_signals = {"user": {"initiative_score": 0.0, "emotional_explicitness": 0.0, "signal_clarity": 0.0, "behaviors": []},
                       "ta": {"initiative_score": 0.0, "emotional_explicitness": 0.0, "signal_clarity": 0.0, "behaviors": []}}
    if new_signals is None:
        new_signals = {"user": {"initiative_score": 0.0, "emotional_explicitness": 0.0, "signal_clarity": 0.0, "behaviors": []},
                       "ta": {"initiative_score": 0.0, "emotional_explicitness": 0.0, "signal_clarity": 0.0, "behaviors": []}}

    # 处理只返回一个人的情况
    for person in ['user', 'ta']:
        if person not in new_signals:
            new_signals[person] = {"behaviors": []}
        if person not in old_signals:
            old_signals[person] = {"behaviors": []}
            
    # 合并 behaviors 列表
    for person in ["user", "ta"]:
        old_behaviors = old_signals[person]["behaviors"]
        new_behaviors = new_signals[person]["behaviors"]
        # 避免重复添加相同的行为，假设行为的唯一性由 action + signal_type + source_ref 决定
        existing_keys = {(b["action"], b["signal_type"], b["source_ref"]) for b in old_behaviors}
        for b in new_behaviors:
            key = (b["action"], b["signal_type"], b["source_ref"])
            if key not in existing_keys:
                old_behaviors.append(b)
                existing_keys.add(key)

    # 更新 initiative_score、emotional_explicitness、signal_clarity
    # v2: 加权平均代替直接覆盖。首轮（旧值=0.0）→ 全量采用；增量 → 旧 0.7 + 新 0.3
    for person in ["user", "ta"]:
        for parameter in ['initiative_score', 'emotional_explicitness', 'signal_clarity']:
            if parameter in new_signals.get(person, {}):
                old_val = old_signals[person].get(parameter, 0.0)
                new_val = new_signals[person][parameter]
                if old_val == 0.0:
                    old_signals[person][parameter] = new_val
                else:
                    old_signals[person][parameter] = round(old_val * 0.7 + new_val * 0.3, 2)

    return old_signals
