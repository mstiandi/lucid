"""
evidence_agent的节点
"""

from ..state.JokerState import JokerState, Claim, EvidenceItem
from langchain.tools import tool
from langchain.messages import SystemMessage, HumanMessage
from tools.loader.load_prompts import load_prompt
from tools.llm.deepseek_llm import llm

@tool
def evidence_return(all_claims: list[dict]) -> dict:
    """
    证据节点的返回值。为每个待验证的 claim 填入从信号中找到的证据。
    Args:
        all_claims (list[dict]): 每个元素对应一个 claim,只需两个字段:
        {
            "content": str,              # claim 原文,必须和输入的 claim content 完全一致,用作合并的 key
            "evidence_from_signals": dict[str, dict]  # 证据字典
        }
        其中 evidence_from_signals 的结构:
        {
            "evidence1": {"content": str, "credit_score": float},
            "evidence2": {"content": str, "credit_score": float},
            ...
        }
        credit_score 范围 0.0-1.0,低于 0.5 表示反驳,高于 0.5 表示支持。
    """
    return {"all_claims": all_claims}

def evidence_node(state: JokerState) -> dict:
    """
    证据节点，根据JokerState中的all_claims参数返回all_claims参数，填入从信号中找到的证据。
    """
    pending_claims = [c for c in state['all_claims'] if c['status'] == 'pending']
    if not pending_claims:
        return {}
    
    # 调用 llm 获取证据
    needed_claims = "\n".join([f"Claim: {c['content']}" for c in pending_claims])
    all_signals = state.get('all_signals', {})
    response = llm.bind_tools([evidence_return]).invoke(
        [SystemMessage(content=load_prompt("evidence_prompt.md") + 
                       "所有status为pending的待验证的claims如下:\n" + needed_claims + "\n所有的信号如下:\n" + str(all_signals))
                       ])
    
    if response.tool_calls:
        tool_call = response.tool_calls[-1]
        args = tool_call["args"]
        updated_claims = args.get("all_claims", []) # 经过验证信息更新的 claims
        for c in updated_claims:
            c['analysed_by'] = ["evidence_agent"] # args中没有analysed_by字段，直接添加
        return {"all_claims": updated_claims}
        

    else:
        # print("没有tool_calls，返回默认值")  
        return {}