"""
对应architect_graph中的thought_v0.md的架构图实现一个最简单的agent
"""

# 导包
from langchain_openai import ChatOpenAI
import os
from typing import TypedDict, Annotated, Literal
from langgraph.graph import StateGraph, add_messages
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.tools import tool

# 创建LLM
llm = ChatOpenAI(
    model = "deepseek-chat",
    api_key = os.environ['DEEPSEEK_API_KEY'],
    base_url = "https://api.deepseek.com/v1"
)

# 加载各个提示词
def load_prompt(filename: str) -> str:
    """从 prompts 目录加载 prompt 文件"""
    prompts_dir = os.path.join(os.path.dirname(__file__), "..", "prompts")
    with open(os.path.join(prompts_dir, filename), "r", encoding="utf-8") as f:
        return f.read().strip()
# os.path.dirname(__file__) 获取当前文件的目录，即D:\my_joker\specific_achievement
# ..是上一级目录，即D:\my_joker

alternative_explanation_prompt = load_prompt("alternative_explanation_prompt.md")
asymmetric_feedback_prompt = load_prompt("asymmetric_feedback_prompt.md")
contradictory_registration_prompt = load_prompt("contradictory_registration_prompt.md")
evidence_prompt = load_prompt("evidence_prompt.md")
information_symmetry_prompt = load_prompt("information_symmetry_prompt.md")
reflexion_prompt = load_prompt("reflexion_prompt.md")
signal_prompt = load_prompt("signal_prompt.md")
supervisor_prompt = load_prompt("supervisor_prompt.md")
summary_prompt = load_prompt("summary_prompt.md")

# 定义route的拼接函数
def add_route(left: list, right: list) -> list:
    """将两个列表拼接起来"""
    return left + right

# State schema：
class ThoughtV0State(TypedDict):
    messages: Annotated[list, add_messages]  # 消息列表，追加式 add_messages是针对list[Message]的一个装饰器，表示这个字段是一个消息列表，每次调用agent时，会将新的消息追加到这个列表中
    route: Annotated[list, add_route]  # 记录agent的执行路线
    done: bool # 是否完成
    next_agent: str # 下一个agent的名字
    iteration_count: int  # 当前循环次数，防止死循环
    is_enough: bool  # 是否已经足够了，是否需要继续调用其他agent

# DeepSeek 不支持 structured_output（JSON schema），改用 tool calling 实现强约束
@tool
def select_next_agent(
    next_agent: Literal["signal_agent", "evidence_agent", "contradictory_registration_agent",
                        "asymmetric_feedback_agent", "information_symmetry_agent",
                        "alternative_explanation_agent", "done"]
) -> str:
    """选择下一个要执行的 agent。参数必须是以下值之一：signal_agent, evidence_agent,
    contradictory_registration_agent, asymmetric_feedback_agent, information_symmetry_agent,
    alternative_explanation_agent, done。只有6个维度分析完或不需继续时选择 done。"""
    return next_agent

@tool
def submit_reflection(is_enough: bool, feedback: str) -> str:
    """提交反思结果。is_enough=True 表示分析已足够，可以进入总结；
    is_enough=False 表示还需要继续调用其他 agent。feedback 是改进建议。"""
    return feedback


max_iterations = 4  # 最大迭代次数，防止死循环

# supervisor agent，负责根据信息选择下一个agent
def supervisor_agent(state: ThoughtV0State) -> dict:
    """
    监管者agent，负责根据信息选择下一个agent。
    """
    # 最多跑 4 轮，防止死循环
    current_iter = state.get("iteration_count", 0)
    if current_iter >= max_iterations:
        return {"done": True, "iteration_count": current_iter + 1}

    message = state['messages'][-1] if state['messages'] else "没有消息"
    message = message.content if hasattr(message, 'content') else message
    # 把已调用的 agent 列表传给 supervisor，避免重复
    used = state.get("route", [])
    used_str = "已调用的agent: " + (", ".join(used) if used else "无")
    result = llm.bind_tools([select_next_agent]).invoke(
        [SystemMessage(content=supervisor_prompt),
         HumanMessage(content=f"{used_str}\n\n用户消息: {message}")]
    )
    # 从 tool_call 中提取 next_agent 参数
    next_agent = result.tool_calls[0]["args"]["next_agent"]

    if next_agent == "done":
        return {"done": True, "iteration_count": current_iter + 1}
    else:
        return {"next_agent": next_agent, "done": False,
                "route": [next_agent],
                "iteration_count": current_iter + 1}


# 选择下一个agent的函数，根据state中的next_agent字段，返回下一个agent的名字，或者结束。
def next_node(state: ThoughtV0State) -> str:
    """
    根据state中的next_agent字段，返回下一个agent的名字，或者结束。
    在graph中使用add_conditional_edges判断，将supervisor和其他的节点联系起来
    """
    if state['done']:
        return "done"
    else:
        return state['next_agent']
    
# 下面定义6个维度的agent
# 因为重复过高，直接进行统一化工厂定义
def agent_factory(agent_prompt: str) -> dict:
    def agent_node(state: ThoughtV0State) -> dict:
        message = state['messages'][-1] if state['messages'] else "没有消息"
        message = message.content if hasattr(message, 'content') else message
        result = llm.invoke([
            SystemMessage(content=agent_prompt),
            HumanMessage(content=message)
        ])
        return {"messages": [result]}
    return agent_node

# 下面定义一个反思节点 reflexion_agent，负责对前面所有agent的分析结果进行反思，形成一个完整的分析报告
def reflexion_agent(state: ThoughtV0State) -> dict:
    if state['iteration_count'] >= max_iterations:
        return {"is_enough": True}
    route = state.get("route", [])
    context = f"经过{len(route)}轮分析，以下是各个agent的分析结果：\n"
    for i in range(len(route)):
        context += f"第{i+1}轮分析结果：\n"
        context += f"agent: {route[i]}\n"
        context += f"{state['messages'][i + 1].content if hasattr(state['messages'][i + 1], 'content') else state['messages'][i + 1]}\n"
    result = llm.bind_tools([submit_reflection]).invoke([
        SystemMessage(content=reflexion_prompt),
        HumanMessage(content=context)
    ])
    args = result.tool_calls[0]["args"]
    return {"is_enough": args["is_enough"], "messages": [AIMessage(content=args["feedback"])]}

def reflexion_next_node(state: ThoughtV0State) -> str:
    if state['is_enough']:
        return "summary_agent"
    else:
        return "supervisor_agent"


# 下面定义总结节点，就是在supervisor和END中间插入一个总结节点
def summary_agent(state: ThoughtV0State) -> dict:
    route = state.get("route", [])
    context = f"经过{len(route)}轮分析，以下是各个agent的分析结果：\n"
    for i in range(len(route)):
        context += f"第{i+1}轮分析结果：\n"
        context += f"agent: {route[i]}\n"
        # messages[0] 是用户输入，messages[1..] 是各 agent 的返回
        context += f"{state['messages'][i + 1].content if hasattr(state['messages'][i + 1], 'content') else state['messages'][i + 1]}\n"
    result = llm.invoke([
        SystemMessage(content=summary_prompt),
        HumanMessage(content=context)
    ])
    return {"messages": [result]}

# 下面进行graph的构建
graph = StateGraph(ThoughtV0State)
graph.add_node("supervisor_agent", supervisor_agent)
graph.add_node("signal_agent", agent_factory(signal_prompt))
graph.add_node("evidence_agent", agent_factory(evidence_prompt))
graph.add_node("contradictory_registration_agent", agent_factory(contradictory_registration_prompt))
graph.add_node("asymmetric_feedback_agent", agent_factory(asymmetric_feedback_prompt))
graph.add_node("information_symmetry_agent", agent_factory(information_symmetry_prompt))
graph.add_node("alternative_explanation_agent", agent_factory(alternative_explanation_prompt))
graph.add_node("summary_agent", summary_agent)
graph.add_node("reflexion_agent", reflexion_agent)
graph.add_edge("__start__", "supervisor_agent")
graph.add_conditional_edges("supervisor_agent", next_node, {"done": "reflexion_agent", "signal_agent": "signal_agent", "evidence_agent": "evidence_agent", "contradictory_registration_agent": "contradictory_registration_agent", "asymmetric_feedback_agent": "asymmetric_feedback_agent", "information_symmetry_agent": "information_symmetry_agent", "alternative_explanation_agent": "alternative_explanation_agent"})
# 但是上面的各个agent的next_agent即使都固定到supervisor_agent，但是因为多对一，无法进行一行代码conditional_edges直接判定，所以还是一个一个来吧
graph.add_conditional_edges("reflexion_agent", reflexion_next_node, {"summary_agent": "summary_agent", "supervisor_agent": "supervisor_agent"})
graph.add_edge("signal_agent", "supervisor_agent")
graph.add_edge("evidence_agent", "supervisor_agent")
graph.add_edge("contradictory_registration_agent", "supervisor_agent")
graph.add_edge("asymmetric_feedback_agent", "supervisor_agent")
graph.add_edge("information_symmetry_agent", "supervisor_agent")
graph.add_edge("alternative_explanation_agent", "supervisor_agent")
graph.add_edge("summary_agent", "__end__")

# 不用set_finish_point，因为我们在supervisor_agent中已经设置了done的判断，会通过add_condtional_edges进行判断的

app = graph.compile(checkpointer=MemorySaver())  # 短期记忆，messages只是一次对话的记忆，MemorySaver()是一个短期记忆的checkpointer，保存到内存中，程序结束后就会消失。

config = {"configurable": {"thread_id": "user_ms"}}

for chunk in app.stream({
    "messages": [HumanMessage(content="我认为她并不喜欢我，因为她说对我的感觉更多是朋友。")],
    "route": [],
    "done": False,
    "next_agent": "supervisor_agent",
    "iteration_count": 0,
    "is_enough": False
},
    config = config,
    stream_mode = "updates",
    ):
    print(chunk)