"""
监管节点，决定下一步路由到那些agent，根据JokerState中的all_claims参数返回next_agents参数。
纯代码，不需要调用模型
"""

from ..state.JokerState import JokerState

def supervisor_node(state: JokerState) -> dict:
    """
    决定下一步路由到那些agent，根据JokerState中的all_claims参数返回next_agents参数
    """
    pending = [c for c in state['all_claims'] if c.get('status', 'pending') == 'pending']
    if not pending:
        return {"next_agents": ["summary_agent"]}
    have_both = any(c.get('direction', 'single') == 'both' for c in pending)   # ← 只在 pending 里找
    next_agents = ["evidence_agent", "alternative_explanation_agent"]
    if have_both:
        next_agents.append("information_symmetry_agent")
    return {"next_agents": next_agents}