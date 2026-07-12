"""
summary_agent，总结节点
"""

# schema:
# class JokerState(TypedDict):
#     messages: Annotated[list, add_messages]
#     all_signals: Annotated[AllSignals, all_signals_reducer]
#     all_claims: Annotated[list[Claim], all_claims_reducer]
#     contradictions: Annotated[dict[str, list[ContradictionItem]], contradictions_reducer]  # claim_content -> contradiction_item
#     info_symmetry: Annotated[dict[str, InfoSymmetryItem], info_symmetry_reducer]
#     next_agents: list[str]
#     new_signals: bool  # 覆盖

from ..state.JokerState import JokerState
from tools.loader.load_prompts import load_prompt
from tools.llm.deepseek_llm import llm
from langchain.messages import SystemMessage

def summary_node(state: JokerState) -> dict:
    """
    总结节点，对本轮对话进行总结，返回AIMessage，同时将所有的claims的status更新为analysed。
    """
    pending_claims = [c for c in state['all_claims'] if c['status'] == 'pending']
    # 提取所有的contradictions
    contradictions = state.get('contradictions', {})
    # 从所有的矛盾中提取属于本轮对话的矛盾
    curr_contradictions = {claim_content: reason for claim_content, reason in contradictions.items() if claim_content in [c['content'] for c in pending_claims]}
    curr_info_symmetry = {claim_content: info for claim_content, info in state.get('info_symmetry', {}).items() if claim_content in [c['content'] for c in pending_claims]}
    system_message = load_prompt("summary_prompt.md")
    if pending_claims:
        system_message += "\n\n本轮对话中待处理的claims如下:\n" + "\n".join([f"Claim: {c['content']}" for c in pending_claims])
    if curr_contradictions:
        system_message += "\n\n本轮对话中待处理的claims中存在的矛盾如下:\n" + "\n".join([f"Claim: {claim_content}, Contradictions: {reason}" for claim_content, reason in curr_contradictions.items()])
    if curr_info_symmetry:
        system_message += "\n\n本轮对话中待处理的claims中存在的信息对称性分析结果如下:\n" + "\n".join([f"Claim: {claim_content}, InfoSymmetry: {info}" for claim_content, info in curr_info_symmetry.items()])
    if not pending_claims and not curr_contradictions and not curr_info_symmetry:
        system_message += "\n\n本轮对话中没有待处理的claims，也没有矛盾和信息对称性分析结果。"
    
    # AIMessage，这个就是用于回答的东西
    response = llm.invoke([
        SystemMessage(content=system_message)
    ])

    # 将所有的claims的status更新为analysed
    updated_claims = [{
        "content": c["content"],
        "analysed_by": ["summary_agent"],
        "status": "analysed"
    } for c in pending_claims]

    return {"messages": [response], "all_claims": updated_claims}