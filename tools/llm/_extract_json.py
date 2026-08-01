"""
从 LLM 文本回复中提取 JSON 对象。三层 fallback 防御。
所有节点统一使用此函数，不再各自复制一份。
"""
import json
import re


def extract_json(text: str) -> dict | None:
    """从 LLM 文本回复中提取 JSON 对象。

    三层 fallback：
    1. json.loads 直接解析（理想情况：LLM 输出纯 JSON）
    2. 正则提取 ```json ``` 代码块（LLM 习惯用 markdown 包裹）
    3. 找第一个 { 到最后一个 }（LLM 在 JSON 前后写了废话）
    """
    # 第 1 层：直接解析
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    # 第 2 层：正则提取 ```json ... ``` 代码块
    m = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 第 3 层：找第一个 { 到最后一个 }
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    return None
