"""
信号处理节点 v2：checklist → 代码算分
LLM 回答 10 道选择题，Python 根据答案计算 initiative_score / emotional_explicitness / signal_clarity。
DeepSeek function calling 在复杂嵌套 dict 上不可靠 → 改用纯 JSON 输出（与 evidence/alternative 节点一致）
"""

import json
import hashlib
from tools.llm._extract_json import extract_json

from ..state.JokerState import JokerState, SignalBehavior, PersonSignals, AllSignals
from tools.llm.chat_llm import json_llm as llm
from tools.llm.tracked_llm import invoke_with_tracking
from tools.loader.load_prompts import load_prompt
from tools.logger import get_logger
from tools.reducer import merge_all_signals
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



def _fact_id(person: str, behavior: dict) -> str:
    """幂等 fact key：同一条行为永远同一个 key，重复写覆盖不新增。"""
    key = f"{person}|{behavior.get('signal_type', '')}|{behavior.get('action', '')}|{behavior.get('source_ref', '')}"
    return hashlib.md5(key.encode("utf-8")).hexdigest()[:16]


def _write_facts(store, all_signals: dict) -> None:
    """把本轮新产出的 behaviors 持久化成 fact（出生时记）。"""
    for person in ["user", "ta"]:
        for b in all_signals.get(person, {}).get("behaviors", []):
            store.put(("facts", "main"), _fact_id(person, b), {
                "person": person,
                "action": b.get("action", ""),
                "signal_type": b.get("signal_type", ""),
                "confidence": b.get("confidence", 0.5),
                "source_ref": b.get("source_ref", ""),
            })


def signals_node(state: JokerState, *, store=None) -> dict:
    log = get_logger()
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

    extra = "【只返回JSON，不要任何其他文字。返回格式：{\"user_signals\": {...}, \"ta_signals\": {...}}。】"

    retry_hint = ""

    # DeepSeek function calling 在复杂嵌套 dict 上不可靠 → 改用纯 LLM + JSON 解析
    for attempt in range(3):
        try:
            response = invoke_with_tracking(llm, [
                SystemMessage(content=signals_prompt),
                HumanMessage(content=f"{prefix}\n\n{extra}\n\n{signal_resource_message}{retry_hint}")
            ], node="SIGNALS", attempt=attempt)
            parsed = extract_json(response.content if hasattr(response, 'content') else str(response))
            if parsed and isinstance(parsed, dict):
                user_data = parsed.get("user_signals", {})
                ta_data = parsed.get("ta_signals", {})

                # 防御：LLM 可能把 dict 序列化成 JSON 字符串
                if isinstance(user_data, str):
                    try:
                        user_data = json.loads(user_data)
                    except Exception:
                        user_data = {}
                if isinstance(ta_data, str):
                    try:
                        ta_data = json.loads(ta_data)
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

                log.info("SIGNALS", "LLM 调用成功")

                # === fact 出生时写入 store ===
                if store:
                    _write_facts(store, all_signals)

                # === 显式合并（all_signals 已是普通字段，不再由 reducer 合并） ===
                merged = merge_all_signals(state.get("all_signals"), all_signals)
                return {"all_signals": merged}

            preview = raw_text[:300] if (raw_text := (response.content if hasattr(response, 'content') else str(response))) else "(empty)"
            log.warn("SIGNALS", "JSON 解析失败或 user_signals/ta_signals 缺失", attempt=attempt + 1, raw_preview=preview)
            retry_hint = f"\n\n【上一轮返回的 JSON 格式无效。你的上一轮输出以如下内容开头：\n```\n{preview}\n```\n请确保：1) 所有字符串用双引号包裹 2) 没有末尾多余逗号 3) 所有花括号完整闭合。请重试返回合法 JSON。】"
        except Exception as e:
            log.warn("SIGNALS", "调用异常", attempt=attempt + 1, error=str(e))
            retry_hint = f"\n\n【上一轮调用异常。请重试返回合法 JSON。】"

    return {}


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
    import json as _json
    print(_json.dumps(result, ensure_ascii=False, indent=2))
