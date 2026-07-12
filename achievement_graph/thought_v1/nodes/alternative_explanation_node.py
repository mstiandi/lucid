"""
alternative_explanation_agent
"""

from ..state.JokerState import JokerState, Claim, AlternativeItem
from langchain.tools import tool
from tools.loader.load_prompts import load_prompt
from tools.llm.deepseek_llm import llm
from langchain.messages import SystemMessage

@tool
def alternative_explanation_return(all_claims: list[dict]) -> dict:
    """
    alternative_explanation_agent的返回值。为每个待验证的 claim 填入从信号中找到的 alternative explanations。
    Args:
        all_claims (list[dict]): 每个元素对应一个 claim,只需两个字段:
        {
            "content": str,              # claim 原文,必须和输入的 claim content 完全一致,用作合并的 key
            "alternative_explanations": dict[str, dict]  # alternative explanations 字典
        }
        其中 alternative_explanations 的结构:
        {
            signal_info1: {"youthink": str, "alternative": str}, # signal_info1 是信号的原话，youthink是你认为的原因，alternative是你认为的 alternative explanation
            signal_info2: {"youthink": str, "alternative": str}, # 如果有多个信号就以此类推，没有不要编写
            ...
        }
    """
    return {"all_claims": all_claims}

def alternative_explanation_node(state: JokerState) -> dict:
    """
    alternative_explanation_agent的节点，根据JokerState中的all_claims参数返回all_claims参数，填入从信号中找到的 alternative explanations。
    """
    pending_claims = [c for c in state["all_claims"] if c["status"] == "pending"]

    if not pending_claims:
        return {}
    
    # 调用 llm 获取 alternative explanations
    needed_claims = "\n".join([f"Claim: {c['content']}" for c in pending_claims])
    all_signals = state.get("all_signals", {})
    response = llm.bind_tools([alternative_explanation_return]).invoke(
        [SystemMessage(content=load_prompt("alternative_explanation_prompt.md") + 
                       "所有status为pending的待验证的claims如下:\n" + needed_claims + "\n所有的信号如下:\n" + str(all_signals))
                       ])
    
    if not response.tool_calls:
        return {}

    tool_call = response.tool_calls[-1]
    args = tool_call["args"]
    updated_claims = args.get("all_claims", []) # 经过验证信息更新的 claims
    for c in updated_claims:
        c['analysed_by'] = ["alternative_explanation_agent"] # args中没有analysed_by字段，直接添加
    return {"all_claims": updated_claims}
