"""
information_symmetry_agent
"""

from ..state.JokerState import JokerState, InfoSymmetryItem
from langchain.tools import tool
from tools.loader.load_prompts import load_prompt
from tools.llm.deepseek_llm import llm
from langchain.messages import SystemMessage

@tool
def information_symmetry_return(info_symmetry: dict[str, InfoSymmetryItem]) -> dict:
    """
    information_symmetry_agent的返回值。为每个claim填入信息对称性分析结果。
    Args:
        info_symmetry (dict[str, InfoSymmetryItem]): 
        键str是claim的content，值是InfoSymmetryItem，结构如下：
        {
            "from_": str,  # "user" | "ta"
            "user_knew": bool,
            "ta_knew": bool,
            "is_sufficient": bool
        }
    """
    return {"info_symmetry": info_symmetry}

def information_symmetry_node(state: JokerState) -> dict:
    """
    information_symmetry_agent的节点，根据JokerState中的all_claims参数返回info_symmetry参数，填入信息对称性分析结果。
    """
    pending_claims = [c for c in state["all_claims"] if c["status"] == "pending"]
    info_symmetry_claims = [c for c in pending_claims if c["direction"] == "both"]
    if not info_symmetry_claims:
        return {}
    
    needed_claims = "\n".join([f"Claim: {c['content']}" for c in info_symmetry_claims])
    all_signals = state.get("all_signals", {})

    response = llm.bind_tools([information_symmetry_return]).invoke(
        [SystemMessage(content=load_prompt("information_symmetry_prompt.md") + 
                       "所有direction为both的待处理的claims如下:\n" + needed_claims + "\n所有的信号如下:\n" + str(all_signals))
                       ])
    
    if not response.tool_calls:
        return {}

    tool_call = response.tool_calls[-1]
    args = tool_call["args"]
    updated_info_symmetry = args.get("info_symmetry", []) # 经过验证信息更新的 info_symmetry
    updated_claims = [{
        "content": c["content"],
        "analysed_by": ["information_symmetry_agent"],
    } for c in info_symmetry_claims]

    return {"info_symmetry": updated_info_symmetry, "all_claims": updated_claims}
    # 不同的字段走不同的reducer，所以不需要担心info_symmetry_reducer无法兼容all_claims
