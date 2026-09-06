"""
将所有的节点和边的状态信息存储在一个统一的结构中，构成graph
"""

from .state.JokerState import JokerState # 这个点.应该是相对于当前的文件而言的
from langgraph.graph import StateGraph
from .nodes import alternative_explanation_node, compression_node, contradictory_registration_node, evidence_node, information_symmetry_node, preprocess_node, supervisor_node, summary_node, signals_node
from langgraph.checkpoint.memory import MemorySaver
from tools.memory import SqliteStore

VALID_AGENTS = {
    "evidence_agent": "evidence_node",
    "alternative_explanation_agent": "alternative_explanation_node",
    "information_symmetry_agent": "information_symmetry_node",
    "summary_agent": "summary_node"
}

def route_fn(state: JokerState) -> list[str]:
    """
    根据JokerState中的next_agents参数返回下一步的路由节点列表。
    过滤掉不在 VALID_AGENTS 中的名称，防止 supervisor 返回未知 agent 名导致静默忽略或报错。
    """
    return [a for a in state['next_agents'] if a in VALID_AGENTS]


graph = StateGraph(JokerState)


graph.add_node("preprocess_node", preprocess_node)
graph.add_node("alternative_explanation_node", alternative_explanation_node)
graph.add_node("contradictory_registration_node", contradictory_registration_node)
graph.add_node("evidence_node", evidence_node)
graph.add_node("information_symmetry_node", information_symmetry_node)
graph.add_node("supervisor_node", supervisor_node)
graph.add_node("compression_node", compression_node)
graph.add_node("summary_node", summary_node)
graph.add_node("signals_node", signals_node)

graph.add_edge("__start__", "preprocess_node")
graph.add_edge("preprocess_node", "signals_node")
graph.add_edge("preprocess_node", "supervisor_node")
graph.add_edge("supervisor_node", "compression_node")
graph.add_conditional_edges("compression_node", route_fn, VALID_AGENTS)
graph.add_edge("evidence_node", "contradictory_registration_node")
graph.add_edge("alternative_explanation_node", "contradictory_registration_node")
graph.add_edge("information_symmetry_node", "contradictory_registration_node")
graph.add_edge("contradictory_registration_node", "summary_node")
graph.add_edge("summary_node", "__end__")

app = graph.compile(checkpointer=MemorySaver(), store=SqliteStore("joker_store.db"))