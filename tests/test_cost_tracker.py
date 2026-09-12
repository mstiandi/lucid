"""M3 成本记账：累加器 + 报表的单元测试。

验证意图：每次 LLM 调用按 attempt 分流记账（首次 vs 重试），
重试多烧的 token / 延迟单独累计，报表能算出 retry_token_ratio 且总 token 为 0 时不除零。
"""
import pytest

from tools.llm.cost_tracker import start_run, reset_run, record, get_usage
from tools.llm.cost_report import format_usage, usage_to_dict


@pytest.fixture(autouse=True)
def _clean_run_usage():
    yield
    reset_run()


def test_record_accumulates_per_node_and_splits_retry():
    """同一节点多次调用累计；attempt>=1 的那次单独计入 retry_*。"""
    start_run()
    record("EVIDENCE", 2400, 600, 4000, attempt=0)
    record("EVIDENCE", 2400, 650, 4500, attempt=1)  # 重试
    usage = get_usage()

    ev = usage.nodes["EVIDENCE"]
    assert ev.calls == 2
    assert ev.input_tokens == 4800        # 2400 + 2400
    assert ev.output_tokens == 1250       # 600 + 650
    assert ev.retries == 1
    assert ev.retry_input_tokens == 2400  # 只有重试那次
    assert ev.retry_output_tokens == 650
    assert ev.latency_ms == 8500
    assert ev.retry_latency_ms == 4500


def test_attempt_zero_is_not_retry():
    """首次尝试不计入重试。"""
    start_run()
    record("SUMMARY", 100, 50, 1000, attempt=0)
    usage = get_usage()

    su = usage.nodes["SUMMARY"]
    assert su.calls == 1
    assert su.retries == 0
    assert su.retry_tokens == 0


def test_retry_token_ratio_is_subset_ratio():
    """retry_token_ratio = retry_tokens / total_tokens，是占比不是独立总数。"""
    start_run()
    record("E", 2400, 600, 1000, attempt=0)
    record("E", 2400, 650, 1000, attempt=1)
    usage = get_usage()

    assert usage.nodes["E"].retry_token_ratio == 0.5  # 3050 / 6050


def test_retry_token_ratio_none_when_total_zero():
    """usage 缺失时总 token 为 0，占比返回 None 而非除零。"""
    start_run()
    record("E", None, None, 1000, attempt=0)
    usage = get_usage()

    assert usage.nodes["E"].retry_token_ratio is None
    assert usage.nodes["E"].missing_usage == 1


def test_record_noop_without_run():
    """未开账本时 record 是 no-op，不抛异常。"""
    record("E", 100, 50, 1000, attempt=0)
    assert get_usage() is None


def test_total_aggregates_nodes():
    """TOTAL 行 = 所有节点的加总。"""
    start_run()
    record("A", 100, 50, 100, attempt=0)
    record("B", 200, 100, 200, attempt=0)
    usage = get_usage()

    t = usage.total()
    assert t.input_tokens == 300
    assert t.output_tokens == 150
    assert t.calls == 2


def test_format_usage_and_to_dict():
    """报表文本 + 结构化 dict 都产出，且含 retry_token_ratio。"""
    start_run()
    record("EVIDENCE", 2400, 600, 4000, attempt=0)
    record("EVIDENCE", 2400, 650, 4500, attempt=1)
    usage = get_usage()

    text = format_usage(usage)
    assert "EVIDENCE" in text
    assert "TOTAL" in text
    assert "retry_ratio=0.50" in text

    d = usage_to_dict(usage)
    assert d["total"]["retry_token_ratio"] == 0.5
    assert d["nodes"]["EVIDENCE"]["retry_tokens"] == 3050


def test_set_run_id_starts_and_resets_usage():
    """set_run_id 联动账本：有效 run_id 开账本，None 丢弃。"""
    from tools.logger import set_run_id

    set_run_id("r1")
    record("E", 100, 50, 1000, attempt=0)
    assert get_usage() is not None
    assert get_usage().total().total_tokens == 150

    set_run_id(None)
    assert get_usage() is None
