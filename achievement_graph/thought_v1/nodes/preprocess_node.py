"""
预处理节点，根据HumanMessage的内容，返回new_signals:bool和claims:dict[str, Claim]，
通过Annotated并入all_claims
"""

from langchain.tools import tool
from ..state.JokerState import JokerState # 都要升级到my_joker下一级的地步，因为运行的时候是D:\my_joker
from tools.loader.load_prompts import load_prompt
from tools.llm.deepseek_llm import llm
from langchain.messages import SystemMessage, HumanMessage

@tool
def preprocess_return(new_signals: bool, claims: list[dict]) -> dict:
    """
    预处理节点的返回值，返回一个字典，包含new_signals和claims。
    Args:
        new_signals (bool): 判断信息中是否有新的信号。
        claims (list[dict]): 判断信息中是否有新的claims。其中dict的结构如下：
        {
            "content": str,
            "direction": "single" | "both",
            "analysed_by": list[str],
            "status": "pending" | "analysed",
            "evidence_from_signals": dict[str, dict],
            "alternative_explanations": dict[str, dict]
        }
    """
    return {"new_signals": new_signals, "claims": claims}


def preprocess_node(state: JokerState) -> dict:
    """
    预处理节点，根据HumanMessage的内容，返回new_signals:bool和claims:list[Claim]
    """
    human_message = state['messages'][-1] if state['messages'] else "没有消息"
    human_message = human_message.content if hasattr(human_message, 'content') else human_message
    response = llm.bind_tools([preprocess_return]).invoke(
        [SystemMessage(content=load_prompt("preprocess_prompt.md")),
         HumanMessage(content=human_message)]
    )
    if response.tool_calls:
        tool_call = response.tool_calls[0]
        args = tool_call["args"]
        new_signals = args.get("new_signals", False)
        claims = args.get("claims", [])
        for c in claims:
            c.setdefault("analysed_by", [])
            c.setdefault("status", "pending")
            c.setdefault("evidence_from_signals", {})
            c.setdefault("alternative_explanations", {})
        return {"new_signals": new_signals, "all_claims": claims}
    else:
        # print("没有tool_calls，返回默认值")
        return {"new_signals": False, "all_claims": []}
    