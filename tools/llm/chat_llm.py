from langchain_openai import ChatOpenAI
import os

llm = ChatOpenAI(
    model="deepseek-chat",
    api_key=os.environ['DEEPSEEK_API_KEY'],
    base_url="https://api.deepseek.com/v1",
    temperature=0,  # 裁判模型需要确定性输出，消除评分方差
)
