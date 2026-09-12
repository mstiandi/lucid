"""
共享 LLM 调用工具：重试 + 结构化日志
所有 LLM 调用节点统一使用此函数，替代裸 llm.bind_tools().invoke()
"""
import time

from tools.logger import get_logger


def safe_llm_call(llm, tools: list, messages: list, node_name: str = "LLM", max_retries: int = 2):
    """调用 LLM（带 bind_tools），tool_calls 为空 → 重试，全失败 → 返回 None。

    Args:
        llm: ChatOpenAI 实例
        tools: bind_tools 的工具列表
        messages: SystemMessage/HumanMessage 列表
        node_name: 用于日志前缀，如 "EVIDENCE"
        max_retries: 最大重试次数（总共 max_retries+1 次尝试）

    Returns:
        成功 → AIMessage（response.tool_calls 非空）
        失败 → None
    """
    log = get_logger()
    start = time.time()

    for attempt in range(max_retries + 1):
        try:
            response = llm.bind_tools(tools).invoke(messages)

            # token 用量
            n_tokens = "?"
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                n_tokens = response.usage_metadata.get('total_tokens', '?')

            elapsed = time.time() - start

            if response.tool_calls:
                log.info(node_name, "LLM 调用成功",
                         tokens=n_tokens, retries=attempt, latency=round(elapsed, 1))
                return response
            else:
                if attempt < max_retries:
                    log.warn(node_name, "tool_calls 为空，重试中",
                             attempt=f"{attempt+1}/{max_retries}")
                else:
                    log.warn(node_name, "所有重试均返回空 tool_calls",
                             total_attempts=max_retries + 1)

        except Exception as e:
            elapsed = time.time() - start
            if attempt < max_retries:
                log.warn(node_name, f"调用失败，重试中",
                         attempt=f"{attempt+1}/{max_retries}", error=str(e), latency=round(elapsed, 1))
            else:
                log.error(node_name, f"所有重试全部失败",
                          total_attempts=max_retries + 1, error=str(e), latency=round(elapsed, 1))

    return None


async def safe_llm_call_async(llm, tools: list, messages: list, node_name: str = "LLM", max_retries: int = 2):
    """safe_llm_call 的异步版：ainvoke + await，供 asyncio.gather 并发调用。

    与同步版唯一区别：`llm.bind_tools(tools).invoke(messages)` → `await ...ainvoke(messages)`。
    重试、日志、token 记账逻辑完全一致。
    """
    log = get_logger()
    start = time.time()

    for attempt in range(max_retries + 1):
        try:
            response = await llm.bind_tools(tools).ainvoke(messages)

            # token 用量
            n_tokens = "?"
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                n_tokens = response.usage_metadata.get('total_tokens', '?')

            elapsed = time.time() - start

            if response.tool_calls:
                log.info(node_name, "LLM 调用成功",
                         tokens=n_tokens, retries=attempt, latency=round(elapsed, 1))
                return response
            else:
                if attempt < max_retries:
                    log.warn(node_name, "tool_calls 为空，重试中",
                             attempt=f"{attempt+1}/{max_retries}")
                else:
                    log.warn(node_name, "所有重试均返回空 tool_calls",
                             total_attempts=max_retries + 1)

        except Exception as e:
            elapsed = time.time() - start
            if attempt < max_retries:
                log.warn(node_name, f"调用失败，重试中",
                         attempt=f"{attempt+1}/{max_retries}", error=str(e), latency=round(elapsed, 1))
            else:
                log.error(node_name, f"所有重试全部失败",
                          total_attempts=max_retries + 1, error=str(e), latency=round(elapsed, 1))

    return None
