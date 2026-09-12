"""
统一的 LLM 调用追踪：每次调用（含重试的每次尝试）记录 token 用量 + 延迟 + attempt 序号。

所有节点的 llm.invoke 都走这里，替换裸 invoke。用法：
    response = invoke_with_tracking(llm, [SystemMessage(...)], node="EVIDENCE", attempt=attempt)

记账口径（两级）：
- per-call：每条日志记单次 input/output/total tokens + latency_ms + attempt
- per-node 聚合：由 M3 消费日志时对同一 node 的 attempt 求和，得到"重试放大几倍"
"""

import time

from tools.logger import get_logger
from tools.llm.cost_tracker import record


def _extract_usage(response) -> dict:
    """从 AIMessage 提取 token 用量。usage_metadata 缺失时各字段为 None（记账缺口）。"""
    um = getattr(response, "usage_metadata", None) or {}
    return {
        "input_tokens": um.get("input_tokens"),
        "output_tokens": um.get("output_tokens"),
        "total_tokens": um.get("total_tokens"),
    }


def invoke_with_tracking(llm, messages, *, node: str, attempt: int = 0):
    """调用 llm.invoke 并记录 token/延迟。返回 response（与裸 invoke 完全一致，drop-in 替换）。"""
    log = get_logger()
    start = time.perf_counter()
    response = llm.invoke(messages)
    latency_ms = round((time.perf_counter() - start) * 1000)

    usage = _extract_usage(response)
    record(node, usage["input_tokens"], usage["output_tokens"], latency_ms, attempt)
    log.info(node, "LLM调用", attempt=attempt, latency_ms=latency_ms, **usage)
    return response
