from langchain_openai import ChatOpenAI
import os

llm = ChatOpenAI(
    model="deepseek-chat",
    api_key=os.environ['DEEPSEEK_API_KEY'],
    base_url="https://api.deepseek.com/v1"
)
