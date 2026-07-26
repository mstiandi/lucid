"""
预处理节点 v2：checklist → 代码判定 direction
LLM 回答 2 道选择题，Python 根据答案判定 single/both。
DeepSeek function calling 在复杂嵌套 dict 上不可靠 → 改用纯 JSON 输出（与 evidence/alternative 节点一致）
"""

import json
import re

from ..state.JokerState import JokerState
from tools.loader.load_prompts import load_prompt
from tools.llm.deepseek_llm import llm
from tools.logger import get_logger
from langchain.messages import SystemMessage, HumanMessage


def _calc_direction(checklist: dict) -> str:
    """根据 checklist 判定 direction：
    claim_subject == "双方关系" 或 needs_mindreading == "是" → both，否则 single。"""
    subject = checklist.get("claim_subject", "")
    mindread = checklist.get("needs_mindreading", "")
    if subject == "双方关系" or mindread == "是":
        return "both"
    return "single"


def _extract_json(text: str) -> dict | None:
    """从 LLM 文本回复中提取 JSON 对象。处理 ```json ... ``` 包裹或裸 JSON。"""
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    m = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass
    return None


def preprocess_node(state: JokerState, *, store=None) -> dict:
    log = get_logger()
    human_message = state['messages'][-1] if state['messages'] else "没有消息"
    human_message = human_message.content if hasattr(human_message, 'content') else human_message

    extra = "【只返回JSON，不要任何其他文字。返回格式：{\"new_signals\": bool, \"claims\": [...]}。】"

    # DeepSeek function calling 在复杂嵌套 dict 上不可靠 → 改用纯 LLM + JSON 解析
    for attempt in range(3):
        try:
            response = llm.invoke([
                SystemMessage(content=load_prompt("preprocess_prompt.md")),
                HumanMessage(content=f"{extra}\n\n{human_message}")
            ])
            parsed = _extract_json(response.content if hasattr(response, 'content') else str(response))
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

                result = {"new_signals": new_signals, "all_claims": claims}

                # 长期记忆加载：当前 state 无历史 → 从 Store 恢复 profile
                if store:
                    has_history = bool(
                        state.get('all_signals', {}).get('user', {}).get('behaviors')
                        or state.get('all_signals', {}).get('ta', {}).get('behaviors')
                    )
                    if not has_history:
                        profile = store.get(("profiles", "main", "signals"), "latest")
                        if profile:
                            result["all_signals"] = profile.value

                log.info("PREPROCESS", "LLM 调用成功", claims=len(claims))
                return result

            log.warn("PREPROCESS", "JSON 解析失败", attempt=attempt + 1)
        except Exception as e:
            log.warn("PREPROCESS", "调用异常", attempt=attempt + 1, error=str(e))

    return {"new_signals": False, "all_claims": []}
