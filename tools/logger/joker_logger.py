"""
Joker 结构化日志系统（基于 stdlib logging）。

用法：
    from tools.logger import get_logger, set_run_id
    set_run_id(thread_id)          # api.py / runner.py 每轮开始时调用
    log = get_logger()
    log.info("EVIDENCE", "LLM调用", attempt=1, input_tokens=18432)

每条日志同时输出到：
1. 控制台（人类可读）
2. JSONL 文件（结构化，可 grep / jq 分析），每条含 run_id 关联一次调用链

日志文件路径：{project_root}/logs/joker_{timestamp}.jsonl
"""

import contextvars
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from tools.llm.cost_tracker import start_run, reset_run

# 一次调用（一个 thread_id）的关联标识。api.py/runner.py 每轮 set_run_id(thread_id)，
# 之后所有节点日志自动带上这个 run_id，从而把同一轮 preprocess→…→summary 串成一条链。
_run_id_var = contextvars.ContextVar("joker_run_id", default=None)


def set_run_id(run_id: str | None) -> None:
    """设置当前上下文的一次调用标识。"""
    _run_id_var.set(run_id)
    # 联动成本累加器：run_id 有效 → 开新账本；None → 丢弃账本
    if run_id is None:
        reset_run()
    else:
        start_run()


def get_run_id() -> str | None:
    """读取当前上下文的一次调用标识。"""
    return _run_id_var.get()


class _JsonlFormatter(logging.Formatter):
    """把 LogRecord 格式化为一行 JSON（结构化、机器可解析）。"""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.now().isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "run_id": _run_id_var.get(),
            "node": getattr(record, "node", "-"),
            "msg": record.getMessage(),
        }
        data = getattr(record, "data", None)
        if data:
            entry["data"] = data
        return json.dumps(entry, ensure_ascii=False)


class _ConsoleFormatter(logging.Formatter):
    """人类可读的控制台输出。"""

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.now().isoformat(timespec="seconds")
        node = getattr(record, "node", "-")
        return f"{ts} [{node}] {record.levelname} {record.getMessage()}"


class JokerLogger:
    """结构化日志器：stdlib logging + JSONL 文件 + 控制台。"""

    def __init__(self, log_dir: str | Path | None = None):
        if log_dir is None:
            log_dir = Path(__file__).parent.parent.parent / "logs"
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = self.log_dir / f"joker_{timestamp}.jsonl"

        self._logger = logging.getLogger("joker")
        self._logger.setLevel(logging.DEBUG)
        self._logger.propagate = False

        file_handler = logging.FileHandler(self.log_file, encoding="utf-8")
        file_handler.setFormatter(_JsonlFormatter())
        self._logger.addHandler(file_handler)

        # Windows 控制台默认 GBK，中文会乱码 → 重配成 UTF-8
        console_stream = sys.stderr
        try:
            console_stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
        console_handler = logging.StreamHandler(console_stream)
        console_handler.setFormatter(_ConsoleFormatter())
        self._logger.addHandler(console_handler)

    def _emit(self, level: int, node: str, message: str, data: dict) -> None:
        self._logger.log(level, message, extra={"node": node, "data": data})

    def debug(self, node: str, message: str, **data) -> None:
        self._emit(logging.DEBUG, node, message, data)

    def info(self, node: str, message: str, **data) -> None:
        self._emit(logging.INFO, node, message, data)

    def warn(self, node: str, message: str, **data) -> None:
        self._emit(logging.WARNING, node, message, data)

    def error(self, node: str, message: str, **data) -> None:
        self._emit(logging.ERROR, node, message, data)

    @property
    def path(self) -> Path:
        """当前日志文件路径（兼容旧接口）。"""
        return self.log_file

    def close(self) -> None:
        """关闭并移除所有 handler（供 reset_logger / 测试隔离）。"""
        for handler in list(self._logger.handlers):
            handler.close()
            self._logger.removeHandler(handler)


# ── 模块级单例 ──────────────────────────────────────────

_logger: JokerLogger | None = None


def get_logger(log_dir: str | Path | None = None) -> JokerLogger:
    """获取全局 logger 实例。传入 log_dir 时若与当前目录不同则重建。"""
    global _logger
    if _logger is None:
        _logger = JokerLogger(log_dir)
    elif log_dir is not None and _logger.log_dir != Path(log_dir):
        _logger.close()
        _logger = JokerLogger(log_dir)
    return _logger


def reset_logger() -> None:
    """重置 logger（主要用于测试隔离）。"""
    global _logger
    if _logger is not None:
        _logger.close()
    _logger = None
