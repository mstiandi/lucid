"""
信号处理节点，根据预处理的节点对于HumanMessage返回的new_signals进行信号处理，
返回all_signals:AllSignals --- schema如下：
class SignalBehavior(TypedDict):
    action: str
    signal_type: str
    confidence: float
    source_ref: str  # 原话

class PersonSignals(TypedDict):
    initiative_score: float
    emotional_explicitness: float
    signal_clarity: float
    behaviors: list[SignalBehavior]

class AllSignals(TypedDict):
    user: PersonSignals
    ta: PersonSignals

返回值不需要将new_signals改回False，因为每次预处理节点都是覆盖式判断的。
"""

from ..state.JokerState import JokerState, SignalBehavior, PersonSignals, AllSignals    
from tools.llm.deepseek_llm import llm
from tools.loader.load_prompts import load_prompt
from langchain.tools import tool
from langchain.messages import SystemMessage, HumanMessage


signals_prompt = load_prompt("signals_prompt.md")

@tool
def signals_return(all_signals: AllSignals) -> dict:
    """
    信号处理节点的返回值，返回一个字典，包含all_signals。
    Args:
        all_signals (AllSignals): 包含用户和TA的信号信息。
        AllSignals的结构如下：
        {
            "user": {
                "initiative_score": float,
                "emotional_explicitness": float,
                "signal_clarity": float,
                "behaviors": list[SignalBehavior]
            },
            "ta": {
                "initiative_score": float,
                "emotional_explicitness": float,
                "signal_clarity": float,
                "behaviors": list[SignalBehavior]
            }
        }
        SignalBehavior的结构如下：
        {
            "action": str,
            "signal_type": str,
            "confidence": float,
            "source_ref": str  # 原话
        }
    """
    return {"all_signals": all_signals}

def signals_node(state: JokerState) -> dict:
    if not state['new_signals']:
        return {}
    signal_resource_message = state['messages'][-1] if state['messages'] else "没有消息"
    signal_resource_message = signal_resource_message.content if hasattr(signal_resource_message, 'content') else signal_resource_message
    response = llm.bind_tools([signals_return]).invoke([
        SystemMessage(content=signals_prompt),
        HumanMessage(content=signal_resource_message)
    ])
    if response.tool_calls:
        tool_call = response.tool_calls[-1]
        args = tool_call["args"]["all_signals"]
        return {"all_signals": args}
    return {}
    
if __name__ == "__main__":
    # 测试 signals_node
    test_state = JokerState(
        messages=[HumanMessage(content="我邀请她旅游，但是她拒绝了")],
        all_signals=AllSignals(user=PersonSignals(initiative_score=0.5, emotional_explicitness=0.5, signal_clarity=0.5, behaviors=[]),
                                ta=PersonSignals(initiative_score=0.5, emotional_explicitness=0.5, signal_clarity=0.5, behaviors=[])),
        all_claims=[],
        contradictions={},
        info_symmetry={},
        next_agents=[],
        new_signals=True
    )
    result = signals_node(test_state)
    print(result)