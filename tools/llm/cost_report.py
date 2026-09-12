"""
成本汇总报表：把 RunUsage 转成可读文本 / 可 JSON 结构。

- format_usage(usage) -> str   : 控制台 / 日志用的多行文本
- usage_to_dict(usage) -> dict : JSONL / eval report 用的结构化 dict
- log_run_summary()            : 读当前 run 账本，打一条 GRAPH_TOTAL 汇总日志
"""
from tools.llm.cost_tracker import RunUsage, NodeUsage, get_usage


def _node_to_dict(nu: NodeUsage) -> dict:
    return {
        "calls": nu.calls,
        "input_tokens": nu.input_tokens,
        "output_tokens": nu.output_tokens,
        "total_tokens": nu.total_tokens,
        "retries": nu.retries,
        "retry_input_tokens": nu.retry_input_tokens,
        "retry_output_tokens": nu.retry_output_tokens,
        "retry_tokens": nu.retry_tokens,
        "retry_token_ratio": nu.retry_token_ratio,
        "latency_ms": round(nu.latency_ms),
        "retry_latency_ms": round(nu.retry_latency_ms),
        "missing_usage": nu.missing_usage,
    }


def usage_to_dict(usage: RunUsage) -> dict:
    return {
        "nodes": {name: _node_to_dict(nu) for name, nu in usage.nodes.items()},
        "total": _node_to_dict(usage.total()),
    }


def _fmt_node(name: str, nu: NodeUsage) -> str:
    ratio = nu.retry_token_ratio
    ratio_s = f"{ratio:.2f}" if ratio is not None else "-"
    return (f"  {name:<12} in={nu.input_tokens:<6} out={nu.output_tokens:<6} "
            f"calls={nu.calls} retry={nu.retries} "
            f"retry_tok={nu.retry_tokens:<6} retry_ratio={ratio_s} "
            f"t={nu.latency_ms / 1000:.1f}s")


def format_usage(usage: RunUsage) -> str:
    """多行可读报表。"""
    if not usage or not usage.nodes:
        return "（本轮无 LLM 调用）"
    lines = ["本轮 LLM 汇总"]
    for name, nu in usage.nodes.items():
        lines.append(_fmt_node(name, nu))
    lines.append("  " + "─" * 46)
    lines.append(_fmt_node("TOTAL", usage.total()))
    return "\n".join(lines)


def log_run_summary() -> None:
    """读当前 run 的账本，打一条 GRAPH_TOTAL 汇总日志。无账本 / 无调用则跳过。"""
    usage = get_usage()
    if usage is None or not usage.nodes:
        return
    from tools.logger import get_logger  # 延迟导入，避免模块加载顺序问题
    get_logger().info("GRAPH_TOTAL", format_usage(usage), report=usage_to_dict(usage))
