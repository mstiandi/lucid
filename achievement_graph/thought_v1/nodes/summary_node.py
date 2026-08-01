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
from tools.llm.chat_llm import llm
from tools.logger import get_logger
from langchain.messages import SystemMessage, AIMessage

def summary_node(state: JokerState, *, store=None) -> dict:
    """
    总结节点，对本轮对话进行总结，返回AIMessage，同时将所有的claims的status更新为analysed。
    分析完成后将 all_signals + summary 写入长期记忆 Store。
    """
    pending_claims = [c for c in state['all_claims'] if c.get('status', 'pending') == 'pending']
    # 提取所有的contradictions
    contradictions = state.get('contradictions', {})
    # 从所有的矛盾中提取属于本轮对话的矛盾
    curr_contradictions = {claim_content: reason for claim_content, reason in contradictions.items() if claim_content in [c['content'] for c in pending_claims]}
    curr_info_symmetry = {claim_content: info for claim_content, info in state.get('info_symmetry', {}).items() if claim_content in [c['content'] for c in pending_claims]}
    system_message = load_prompt("summary_prompt.md")
    if pending_claims:
        system_message += "\n\n本轮对话中待处理的claims如下:\n" + "\n".join([f"Claim: {c['content']}" for c in pending_claims])
    if curr_contradictions:
        contradiction_lines = []
        for claim_content, items in curr_contradictions.items():
            for item in items:
                tag = "[证据薄弱]" if item.get("type") == "weak_evidence" else "[替代解读]"
                contradiction_lines.append(f"  {tag} {item.get('reason', '?')}")
        system_message += "\n\n本轮对话检测到的弱证据/替代解读如下:\n" + "\n".join(contradiction_lines)
    if curr_info_symmetry:
        system_message += "\n\n本轮对话中待处理的claims中存在的信息对称性分析结果如下:\n" + "\n".join([f"Claim: {claim_content}, InfoSymmetry: {info}" for claim_content, info in curr_info_symmetry.items()])
    alt_gaps = state.get("alt_gaps", [])
    if alt_gaps:
        system_message += "\n\n⚠️ 以下 claim 的替代解释节点未能产出替代解释（可能信号不足或观点本身难以反驳）:\n" + "\n".join([f"- {g}" for g in alt_gaps])
        system_message += "\n请在总结中对这些 claim 的分析结论持保留态度，并提醒用户：这部分分析只基于现有证据的一个方向，可能有其他角度未被覆盖。"
    if not pending_claims and not curr_contradictions and not curr_info_symmetry:
        system_message += "\n\n本轮对话中没有待处理的claims，也没有矛盾和信息对称性分析结果。只需友好回应用户即可，不需要进行分析。"
    
    # AIMessage，这个就是用于回答的东西
    try:
        response = llm.invoke([
            SystemMessage(content=system_message)
        ])
    except Exception as e:
        get_logger().error("SUMMARY", "LLM 调用失败", error=str(e))
        response = None

    # 将所有的claims的status更新为analysed
    updated_claims = [{
        "content": c["content"],
        "analysed_by": ["summary_agent"],
        "status": "analysed"
    } for c in pending_claims]

    if response is None:
        response = AIMessage(content="抱歉，总结生成失败，请重新发送消息。")

    # 长期记忆写入：每轮分析完成后持久化 all_signals + summary
    if store:
        import time as _time
        store.put(("profiles", "main", "signals"), "latest", {
            "user": state["all_signals"]["user"],
            "ta": state["all_signals"]["ta"],
        })
        store.put(("timeline", "main"), f"round_{int(_time.time())}", {
            "summary": response.content if response else "",
            "claims": [c["content"] for c in pending_claims],
        })

    return {"messages": [response], "all_claims": updated_claims}