"""
JOKER —— 恋爱校准官,本地 gradio 前端。v1 版本入口,与 graph.py 并列。
运行: 在 D:\\my_joker 下执行  python -m achievement_graph.thought_v1.app
（因为用了包内相对导入 from .graph，不能再 python app.py 直接跑）
"""
import uuid
import gradio as gr
from langchain.messages import HumanMessage
from .graph import app as graph_app  # 同级 graph.py 里编译好的 LangGraph


def respond(user_msg: str, history: list, thread_id: str):
    """
    一轮对话:把用户输入喂进 graph,取最终 AIMessage 回显。
    thread_id 是本会话的唯一标识 —— MemorySaver 靠它隔离不同会话的多轮状态。
    """
    if not user_msg or not user_msg.strip():
        return history, thread_id, ""

    # 每个会话首轮生成一个 thread_id,之后固定复用 -> 多轮记忆
    if not thread_id:
        thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    # 只传新消息;旧状态由 MemorySaver 按 thread_id 续上
    result = graph_app.invoke({"messages": [HumanMessage(content=user_msg)]}, config=config)
    reply = result["messages"][-1].content if result.get("messages") else "（无回复）"

    history = history + [
        {"role": "user", "content": user_msg},
        {"role": "assistant", "content": reply},
    ]
    return history, thread_id, ""


with gr.Blocks(title="JOKER") as demo:
    gr.Markdown("# JOKER")
    chatbot = gr.Chatbot(height=520)
    thread_id = gr.State("")  # 每个浏览器会话独立持有
    with gr.Row():
        msg = gr.Textbox(
            placeholder="粘贴你们的聊天记录，或补充信息…（发送后分析需几十秒）",
            show_label=False,
            scale=8,
            lines=2,
        )
        send = gr.Button("发送", variant="primary", scale=1)

    send.click(respond, [msg, chatbot, thread_id], [chatbot, thread_id, msg])
    msg.submit(respond, [msg, chatbot, thread_id], [chatbot, thread_id, msg])


if __name__ == "__main__":
    demo.launch(server_name="127.0.0.1", server_port=7860)
