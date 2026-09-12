"""
LLM 调用成本累加器：按 run 聚合每次调用的 token / 重试 / 延迟，供汇总报表消费。

与 JSONL 日志的分工：
- JSONL = 明细（每次调用一行，事后 grep/jq 分析）
- 累加器 = 汇总（graph 跑完直接读总数，实时、不依赖文件 flush）

机制：contextvar 存当前 run 的累加对象，与 set_run_id 同一套（见 tools.logger）。
record() 挂在 invoke_with_tracking / safe_llm_call 里，所有 LLM 调用必经，天然拦截。

记账口径：
- input_tokens / output_tokens = 该节点所有调用（含重试）的 token 总和
- retry_* = attempt >= 1（重试那次）的调用烧掉的 token / 延迟
- retry_token_ratio = retry_tokens / total_tokens（派生值，total 为 0 时 None）
"""
import contextvars
from dataclasses import dataclass, field


@dataclass
class NodeUsage:
    """单个节点的累计用量。"""
    calls: int = 0                 # 总调用次数（含重试）
    input_tokens: int = 0          # 总输入 token
    output_tokens: int = 0         # 总输出 token
    retries: int = 0               # 重试次数（attempt >= 1）
    retry_input_tokens: int = 0    # 重试多烧的输入 token
    retry_output_tokens: int = 0   # 重试多烧的输出 token
    latency_ms: float = 0.0        # 总耗时
    retry_latency_ms: float = 0.0  # 重试多耗的时长
    missing_usage: int = 0         # usage_metadata 缺失的调用次数（token 记 0）

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def retry_tokens(self) -> int:
        return self.retry_input_tokens + self.retry_output_tokens

    @property
    def retry_token_ratio(self):
        """重试多烧的 token 占比（0.xx）；总 token 为 0 时返回 None（避免除零）。"""
        total = self.total_tokens
        if total <= 0:
            return None
        return round(self.retry_tokens / total, 2)


@dataclass
class RunUsage:
    """一次 run（一轮对话 / 一个 eval scenario）的记账本。"""
    nodes: dict[str, NodeUsage] = field(default_factory=dict)

    def get(self, node: str) -> NodeUsage:
        return self.nodes.setdefault(node, NodeUsage())

    def total(self) -> NodeUsage:
        """所有节点的聚合（报表 TOTAL 行）。"""
        t = NodeUsage()
        for nu in self.nodes.values():
            t.calls += nu.calls
            t.input_tokens += nu.input_tokens
            t.output_tokens += nu.output_tokens
            t.retries += nu.retries
            t.retry_input_tokens += nu.retry_input_tokens
            t.retry_output_tokens += nu.retry_output_tokens
            t.latency_ms += nu.latency_ms
            t.retry_latency_ms += nu.retry_latency_ms
            t.missing_usage += nu.missing_usage
        return t


_run_usage_var = contextvars.ContextVar("joker_run_usage", default=None)


def start_run() -> None:
    """开一本新账本（set_run_id 时联动调用）。"""
    _run_usage_var.set(RunUsage())


def reset_run() -> None:
    """丢弃账本（set_run_id(None) 时联动调用）。"""
    _run_usage_var.set(None)


def record(node: str, input_tokens, output_tokens, latency_ms: float, attempt: int) -> None:
    """记一次 LLM 调用。未开账本（无 run 上下文）时为 no-op。

    attempt: 0 = 首次尝试，>=1 = 重试。重试的 token / 延迟单独计入 retry_*。
    """
    usage = _run_usage_var.get()
    if usage is None:
        return
    nu = usage.get(node)
    nu.calls += 1

    it = int(input_tokens) if input_tokens else 0
    ot = int(output_tokens) if output_tokens else 0
    nu.input_tokens += it
    nu.output_tokens += ot
    nu.latency_ms += latency_ms

    if input_tokens is None or output_tokens is None:
        nu.missing_usage += 1

    if attempt > 0:
        nu.retries += 1
        nu.retry_input_tokens += it
        nu.retry_output_tokens += ot
        nu.retry_latency_ms += latency_ms


def get_usage() -> "RunUsage | None":
    """读当前 run 的账本；未开账本返回 None。"""
    return _run_usage_var.get()
