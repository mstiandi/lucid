from langchain_openai import ChatOpenAI
import os
import httpx

_common = dict(
    model="deepseek-v4-flash",
    api_key=os.environ['DEEPSEEK_API_KEY'],
    base_url="https://api.deepseek.com/v1",
    temperature=0,  # 确定性输出，消除评分方差
    # trust_env=False：忽略系统代理环境变量。DeepSeek 是国产 API，直连即可；
    # 否则机器上若配了 http_proxy 但代理没运行，会连不上（Connection error）。
    http_client=httpx.Client(trust_env=False, timeout=300.0),
)

llm = ChatOpenAI(**_common)

# 纯 JSON 输出节点专用：response_format 让 API 层强制返回合法 JSON，
# 消除「截断 / 前后加废话 / 花括号不闭合」这类解析失败。
# 注意：不能给裁判（tool calling）用——json_object 与 tools 互斥。
json_llm = ChatOpenAI(**_common, model_kwargs={"response_format": {"type": "json_object"}})
