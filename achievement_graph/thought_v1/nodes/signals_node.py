"""
信号处理节点 v2：checklist → 代码算分
LLM 回答 10 道选择题，Python 根据答案计算 initiative_score / emotional_explicitness / signal_clarity。
"""

from ..state.JokerState import JokerState, SignalBehavior, PersonSignals, AllSignals
from tools.llm.deepseek_llm import llm
from tools.llm.safe_llm_call import safe_llm_call
from tools.loader.load_prompts import load_prompt
from langchain.tools import tool
from langchain.messages import SystemMessage, HumanMessage


signals_prompt = load_prompt("signals_prompt.md")

# === Checklist 选项 → 分值映射 ===
CHECKLIST_MAP = {
    # 主动性
    "initiates_frequently": {"经常": 1.0, "偶尔": 0.5, "很少": 0.0},
    "initiates_meetups":    {"是": 1.0, "否": 0.0},
    "sustains_dialogue":    {"是": 1.0, "部分": 0.5, "否": 0.0},
    "expresses_needs":      {"明确": 1.0, "暗示": 0.5, "无": 0.0},
    # 情感表达清晰度
    "expresses_emotion":    {"明确": 1.0, "暗示": 0.5, "回避": 0.0},
    "language_intensity":   {"高": 1.0, "中": 0.5, "低": 0.0},
    "perceptibility":       {"能": 1.0, "模糊": 0.5, "不能": 0.0},
    # 信号清晰度
    "directness":           {"直接": 1.0, "间接": 0.5, "隐晦": 0.0},
    "ambiguity":            {"1种解读": 1.0, "2种解读": 0.5, "≥3种解读": 0.0},
    "consistency":          {"一致": 1.0, "部分一致": 0.5, "不一致": 0.0},
}

INITIATIVE_DIMS = ["initiates_frequently", "initiates_meetups", "sustains_dialogue", "expresses_needs"]
EMOTIONAL_DIMS = ["expresses_emotion", "language_intensity", "perceptibility"]
CLARITY_DIMS   = ["directness", "ambiguity", "consistency"]

# === Behavior checklist → confidence ===
BEHAVIOR_CHECKLIST_MAP = {
    "behavior_certainty": {"明确陈述": 1.0, "推测": 0.5, "暗示": 0.3},
    "source_directness":  {"原话直接引用": 1.0, "用户转述": 0.7, "二次转述": 0.5},
}
BEHAVIOR_DIMS = ["behavior_certainty", "source_directness"]


def _calc_score(checklist: dict, dims: list[str]) -> float:
    """从 checklist 答案计算等权平均分。LLM 返回了不在选项中的值 → 兜底 0.5。"""
    scores = []
    for dim in dims:
        answer = checklist.get(dim, "")
        score = CHECKLIST_MAP.get(dim, {}).get(answer)
        if score is None:
            score = 0.5  # LLM 返回异常值，取中性分
        scores.append(score)
    return round(sum(scores) / len(scores), 2)


def _calc_behavior_confidence(behavior: dict) -> dict:
    """将 behavior 的 checklist 转换为 confidence，pop checklist 防止污染。"""
    checklist = behavior.pop("checklist", {})
    if isinstance(checklist, dict) and checklist:
        scores = []
        for dim in BEHAVIOR_DIMS:
            answer = checklist.get(dim, "")
            score = BEHAVIOR_CHECKLIST_MAP.get(dim, {}).get(answer)
            if score is None:
                score = 0.5
            scores.append(score)
        behavior["confidence"] = round(sum(scores) / len(scores), 2)
    else:
        behavior["confidence"] = 0.5  # 无 checklist → 中性兜底
    return behavior


@tool
def signals_return(user_signals: dict, ta_signals: dict) -> dict:
    """
    返回用户和对方的信号分析结果（checklist 答案 + 行为提取），由代码据此算分。

    user_signals / ta_signals 结构完全相同：
    {
        "initiative_checklist": {
            "initiates_frequently": "经常|偶尔|很少",
            "initiates_meetups": "是|否",
            "sustains_dialogue": "是|部分|否",
            "expresses_needs": "明确|暗示|无"
        },
        "emotional_checklist": {
            "expresses_emotion": "明确|暗示|回避",
            "language_intensity": "高|中|低",
            "perceptibility": "能|模糊|不能"
        },
        "clarity_checklist": {
            "directness": "直接|间接|隐晦",
            "ambiguity": "1种解读|2种解读|≥3种解读",
            "consistency": "一致|部分一致|不一致"
        },
        "behaviors": [
            {"action": str, "signal_type": str, "confidence": float, "source_ref": str},
            ...
        ]
    }

    注意：
    - checklist 每题必须三选一，不要编造选项外的值
    - behaviors 可空列表（本轮无新行为时传 []）
    """
    return {"user_signals": user_signals, "ta_signals": ta_signals}


def signals_node(state: JokerState) -> dict:
    if not state['new_signals']:
        return {}

    signal_resource_message = state['messages'][-1] if state['messages'] else "没有消息"
    signal_resource_message = signal_resource_message.content if hasattr(signal_resource_message, 'content') else signal_resource_message

    # 判断首轮 / 增量：已有 all_signals 中有无 behaviors
    existing = state.get('all_signals', {})
    has_history = bool(
        existing.get('user', {}).get('behaviors') or
        existing.get('ta', {}).get('behaviors')
    )

    if has_history:
        prefix = "【增量模式】以下是新增信息。请仅基于新增内容回答 checklist 和提取 behaviors。"
    else:
        prefix = "【首轮模式】请基于以下内容进行完整的信号分析。"

    response = safe_llm_call(llm, [signals_return], [
        SystemMessage(content=signals_prompt),
        HumanMessage(content=f"{prefix}\n\n{signal_resource_message}")
    ], node_name="SIGNALS")

    if response is None:
        return {}

    tool_call = response.tool_calls[-1]
    args = tool_call["args"]
    user_data = args.get("user_signals", {})
    ta_data   = args.get("ta_signals", {})

    # 防御：LLM 可能把 dict 参数序列化成 JSON 字符串
    if isinstance(user_data, str):
        try:
            import json as _json
            user_data = _json.loads(user_data)
        except Exception:
            user_data = {}
    if isinstance(ta_data, str):
        try:
            import json as _json
            ta_data = _json.loads(ta_data)
        except Exception:
            ta_data = {}

    user_behaviors = [_calc_behavior_confidence(b) for b in user_data.get("behaviors", [])]
    ta_behaviors   = [_calc_behavior_confidence(b) for b in ta_data.get("behaviors", [])]

    # === 代码算分 ===
    all_signals = {
        "user": {
            "initiative_score":       _calc_score(user_data.get("initiative_checklist", {}), INITIATIVE_DIMS),
            "emotional_explicitness": _calc_score(user_data.get("emotional_checklist", {}), EMOTIONAL_DIMS),
            "signal_clarity":         _calc_score(user_data.get("clarity_checklist", {}),   CLARITY_DIMS),
            "behaviors":              user_behaviors,
        },
        "ta": {
            "initiative_score":       _calc_score(ta_data.get("initiative_checklist", {}), INITIATIVE_DIMS),
            "emotional_explicitness": _calc_score(ta_data.get("emotional_checklist", {}), EMOTIONAL_DIMS),
            "signal_clarity":         _calc_score(ta_data.get("clarity_checklist", {}),   CLARITY_DIMS),
            "behaviors":              ta_behaviors,
        },
    }

    return {"all_signals": all_signals}


if __name__ == "__main__":
    from langchain.messages import HumanMessage

    test_state = {
        "messages": [HumanMessage(content="我邀请她旅游，但是她拒绝了。她今天早上主动给我发了早安。")],
        "all_signals": {
            "user": {"initiative_score": 0.0, "emotional_explicitness": 0.0, "signal_clarity": 0.0, "behaviors": []},
            "ta":   {"initiative_score": 0.0, "emotional_explicitness": 0.0, "signal_clarity": 0.0, "behaviors": []},
        },
        "all_claims": [],
        "contradictions": {},
        "info_symmetry": {},
        "next_agents": [],
        "new_signals": True,
    }
    result = signals_node(test_state)
    import json
    print(json.dumps(result, ensure_ascii=False, indent=2))
