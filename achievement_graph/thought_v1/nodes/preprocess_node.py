"""
预处理节点 v2：checklist → 代码判定 direction
LLM 回答 2 道选择题，Python 根据答案判定 single/both。
"""

from langchain.tools import tool
from ..state.JokerState import JokerState
from tools.loader.load_prompts import load_prompt
from tools.llm.deepseek_llm import llm
from tools.llm.safe_llm_call import safe_llm_call
from langchain.messages import SystemMessage, HumanMessage


def _calc_direction(checklist: dict) -> str:
    """根据 checklist 判定 direction：
    claim_subject == "双方关系" 或 needs_mindreading == "是" → both，否则 single。"""
    subject = checklist.get("claim_subject", "")
    mindread = checklist.get("needs_mindreading", "")
    if subject == "双方关系" or mindread == "是":
        return "both"
    return "single"


@tool
def preprocess_return(new_signals: bool, claims: list[dict]) -> dict:
    """
    预处理节点的返回值。
    Args:
        new_signals (bool): 是否有新的互动信号。
        claims (list[dict]): 用户新表达的观点。每个 dict 结构：
        {
            "content": str,
            "checklist": {
                "claim_subject": "单方行为|对方态度|双方关系",
                "needs_mindreading": "是|否"
            }
        }
        不需要返回 direction / analysed_by / status 等字段，代码会自动填充。
    """
    return {"new_signals": new_signals, "claims": claims}


def preprocess_node(state: JokerState, *, store=None) -> dict:
    human_message = state['messages'][-1] if state['messages'] else "没有消息"
    human_message = human_message.content if hasattr(human_message, 'content') else human_message

    response = safe_llm_call(llm, [preprocess_return],
        [SystemMessage(content=load_prompt("preprocess_prompt.md")),
         HumanMessage(content=human_message)], node_name="PREPROCESS")

    if response is None:
        return {"new_signals": False, "all_claims": []}

    tool_call = response.tool_calls[-1]
    args = tool_call["args"]
    new_signals = args.get("new_signals", False)
    claims = args.get("claims", [])

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

    return result