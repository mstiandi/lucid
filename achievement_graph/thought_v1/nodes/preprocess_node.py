"""
预处理节点 v2：checklist → 代码判定 direction
LLM 回答 2 道选择题，Python 根据答案判定 single/both。
DeepSeek function calling 在复杂嵌套 dict 上不可靠 → 改用纯 JSON 输出（与 evidence/alternative 节点一致）
"""

import json
from tools.llm._extract_json import extract_json

from ..state.JokerState import JokerState
from tools.loader.load_prompts import load_prompt
from tools.llm.chat_llm import json_llm as llm
from tools.logger import get_logger
from langchain.messages import SystemMessage, HumanMessage


def _calc_direction(checklist: dict) -> str:
    """根据 checklist 判定 direction：
    claim_subject == "双方关系" 或 needs_mindreading == "是" → both，否则 single。
    """
    subject = checklist.get("claim_subject", "")
    mindread = checklist.get("needs_mindreading", "")
    if subject == "双方关系" or mindread == "是":
        return "both"
    return "single"



def _deep_merge_identity(old: dict, new: dict) -> dict:
    """字段级合并身份画像：新字段补充，变化字段覆盖。"""
    merged = {"user": dict(old.get("user", {})), "ta": dict(old.get("ta", {}))}
    for person in ["user", "ta"]:
        if isinstance(new.get(person), dict):
            merged[person].update(new[person])
    return merged


def preprocess_node(state: JokerState, *, store=None) -> dict:
    log = get_logger()
    human_message = state['messages'][-1] if state['messages'] else "没有消息"
    human_message = human_message.content if hasattr(human_message, 'content') else human_message

    extra = "【只返回JSON，不要任何其他文字。返回格式：{\"new_signals\": bool, \"claims\": [...], \"identity\": {\"user\": {...}, \"ta\": {...}}}。】"

    retry_hint = ""

    # DeepSeek function calling 在复杂嵌套 dict 上不可靠 → 改用纯 LLM + JSON 解析
    for attempt in range(3):
        try:
            response = llm.invoke([
                SystemMessage(content=load_prompt("preprocess_prompt.md")),
                HumanMessage(content=f"{extra}\n\n{human_message}{retry_hint}")
            ])
            parsed = extract_json(response.content if hasattr(response, 'content') else str(response))
            if parsed and isinstance(parsed, dict):
                new_signals = parsed.get("new_signals", False)
                claims = parsed.get("claims", [])

                for c in claims:
                    # checklist → direction
                    checklist = c.pop("checklist", {})
                    c["direction"] = _calc_direction(checklist) if isinstance(checklist, dict) else "single"
                    # setdefault 补齐
                    c.setdefault("content", "")
                    c.setdefault("analysed_by", [])
                    c.setdefault("status", "pending")
                    c.setdefault("evidence_from_signals", {})
                    c.setdefault("alternative_explanations", {})

                # 身份画像：规范化本轮新提取
                identity = parsed.get("identity", {})
                if not isinstance(identity, dict):
                    identity = {}
                identity = {
                    "user": identity.get("user", {}) if isinstance(identity.get("user"), dict) else {},
                    "ta": identity.get("ta", {}) if isinstance(identity.get("ta"), dict) else {},
                }

                result = {"new_signals": new_signals, "all_claims": claims}

                # 身份画像累积：state 里已有的（session 内）→ 首轮从 store 恢复 → 合并本轮新提取
                existing_identity = state.get("identity") or {"user": {}, "ta": {}}
                if not (existing_identity.get("user") or existing_identity.get("ta")) and store:
                    stored = store.get(("profiles", "main", "identity"), "latest")
                    if stored and isinstance(stored.value, dict):
                        existing_identity = {
                            "user": dict(stored.value.get("user", {})),
                            "ta": dict(stored.value.get("ta", {})),
                        }
                result["identity"] = _deep_merge_identity(existing_identity, identity)

                # 动态画像加载：首轮恢复 scores（不恢复 behaviors，观察走检索）
                if store:
                    has_history = bool(
                        state.get('all_signals', {}).get('user', {}).get('behaviors')
                        or state.get('all_signals', {}).get('ta', {}).get('behaviors')
                    )
                    if not has_history:
                        profile = store.get(("profiles", "main", "scores"), "latest")
                        if profile and isinstance(profile.value, dict):
                            result["all_signals"] = {
                                "user": {**profile.value.get("user", {}), "behaviors": []},
                                "ta": {**profile.value.get("ta", {}), "behaviors": []},
                            }

                log.info("PREPROCESS", "LLM 调用成功", claims=len(claims))
                return result

            preview = raw_text[:300] if (raw_text := (response.content if hasattr(response, 'content') else str(response))) else "(empty)"
            log.warn("PREPROCESS", "JSON 解析失败", attempt=attempt + 1, raw_preview=preview)
            retry_hint = f"\n\n【上一轮返回的 JSON 格式无效。你的上一轮输出以如下内容开头：\n```\n{preview}\n```\n请确保：1) 所有字符串用双引号包裹 2) 没有末尾多余逗号 3) 所有花括号完整闭合。请重试返回合法 JSON。】"
        except Exception as e:
            log.warn("PREPROCESS", "调用异常", attempt=attempt + 1, error=str(e))
            retry_hint = f"\n\n【上一轮调用异常。请重试返回合法 JSON。】"

    return {"new_signals": False, "all_claims": []}
