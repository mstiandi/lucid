"""LLM 调用追踪的冒烟测试：每次调用（含重试）都记 token + 延迟。"""
import json

import pytest

from tools.llm.tracked_llm import _extract_usage, invoke_with_tracking
from tools.logger import get_logger, reset_logger, set_run_id


class FakeResponse:
    """模拟 AIMessage，只带 usage_metadata。"""

    def __init__(self, usage):
        self.usage_metadata = usage
        self.content = ""


class FakeLLM:
    """模拟 llm，invoke 返回固定 response，记录被调用次数。"""

    def __init__(self, response):
        self.response = response
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        return self.response


@pytest.fixture(autouse=True)
def _clean_logger():
    reset_logger()
    set_run_id(None)
    yield
    reset_logger()
    set_run_id(None)


def test_extract_usage_reads_standard_fields():
    resp = FakeResponse({"input_tokens": 100, "output_tokens": 20, "total_tokens": 120})
    assert _extract_usage(resp) == {
        "input_tokens": 100,
        "output_tokens": 20,
        "total_tokens": 120,
    }


def test_extract_usage_none_when_missing():
    """usage_metadata 缺失时字段为 None，不能崩——记账缺口由这里暴露。"""
    resp = FakeResponse(None)
    usage = _extract_usage(resp)
    assert usage["total_tokens"] is None
    assert usage["input_tokens"] is None


def test_invoke_records_token_per_attempt(tmp_path):
    """重试的每次尝试都单独记一条（含 attempt 序号 + token），不合并。"""
    log = get_logger(log_dir=tmp_path)
    llm = FakeLLM(FakeResponse({"input_tokens": 10, "output_tokens": 2, "total_tokens": 12}))

    set_run_id("r1")
    invoke_with_tracking(llm, ["m"], node="EVIDENCE", attempt=0)
    invoke_with_tracking(llm, ["m"], node="EVIDENCE", attempt=1)
    set_run_id(None)

    lines = log.log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2, "两次调用应记两条日志"

    e0, e1 = json.loads(lines[0]), json.loads(lines[1])
    assert e0["data"]["attempt"] == 0 and e0["data"]["input_tokens"] == 10
    assert e1["data"]["attempt"] == 1 and e1["data"]["input_tokens"] == 10
    assert e0["run_id"] == "r1" and e1["run_id"] == "r1"
    assert e0["node"] == "EVIDENCE"


def test_invoke_returns_response_and_records_latency(tmp_path):
    """返回值与裸 llm.invoke 一致（drop-in 替换），且 latency 已记录。"""
    log = get_logger(log_dir=tmp_path)
    llm = FakeLLM(FakeResponse({"total_tokens": 5}))

    response = invoke_with_tracking(llm, ["m"], node="EVIDENCE")
    assert response is llm.response

    entry = json.loads(log.log_file.read_text(encoding="utf-8").strip())
    assert "latency_ms" in entry["data"]
    assert isinstance(entry["data"]["latency_ms"], (int, float))
