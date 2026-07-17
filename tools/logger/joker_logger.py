"""
Joker 结构化日志系统。

用法：
    from tools.logger import get_logger
    log = get_logger()

    log.info("EVIDENCE", "开始分析", claim_count=3)
    log.warn("EVIDENCE", "tool_calls 为空，重试", attempt=1)
    log.error("EVIDENCE", "LLM 调用失败", error=str(e))

每条日志同时输出到：
1. 控制台（彩色、带时间戳）
2. JSONL 文件（结构化，可 grep / jq 分析）

日志文件路径：{project_root}/logs/joker_{timestamp}.jsonl
"""

import json
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any


# ANSI 颜色
_COLORS = {
    "DEBUG": "\033[36m",   # 青色
    "INFO":  "\033[32m",   # 绿色
    "WARN":  "\033[33m",   # 黄色
    "ERROR": "\033[31m",   # 红色
}
_RESET = "\033[0m"


class JokerLogger:
    """结构化日志器。线程安全，同时写控制台和 JSONL 文件。"""

    def __init__(self, log_dir: str | Path = None):
        if log_dir is None:
            # 默认放在项目根目录的 logs/ 下
            project_root = Path(__file__).parent.parent.parent
            log_dir = project_root / "logs"
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = self.log_dir / f"joker_{timestamp}.jsonl"
        self._lock = threading.Lock()

    def _emit(self, level: str, node: str, message: str, **data: Any) -> None:
        """写入日志条目。"""
        entry = {
            "ts":    datetime.now().isoformat(timespec="seconds"),
            "level": level,
            "node":  node,
            "msg":   message,
        }
        if data:
            entry["data"] = data

        # 1. 写文件（JSONL）
        with self._lock:
            try:
                with open(self.log_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            except Exception:
                pass  # 日志写盘失败不抛异常，不干扰主流程

        # 2. 控制台
        color = _COLORS.get(level, "")
        ts = entry["ts"]
        sys.stdout.write(f"{ts} {color}[{node}] {level}{_RESET} {message}\n")
        sys.stdout.flush()

    # ── 便捷方法 ──────────────────────────────────────────

    def debug(self, node: str, message: str, **data: Any) -> None:
        """调试信息。生产环境可关闭。"""
        self._emit("DEBUG", node, message, **data)

    def info(self, node: str, message: str, **data: Any) -> None:
        """正常运行信息。"""
        self._emit("INFO", node, message, **data)

    def warn(self, node: str, message: str, **data: Any) -> None:
        """可恢复的异常/降级。"""
        self._emit("WARN", node, message, **data)

    def error(self, node: str, message: str, **data: Any) -> None:
        """不可恢复的错误。"""
        self._emit("ERROR", node, message, **data)

    @property
    def path(self) -> Path:
        """当前日志文件路径。"""
        return self.log_file


# ── 模块级单例 ──────────────────────────────────────────

_logger: JokerLogger | None = None


def get_logger(log_dir: str | Path = None) -> JokerLogger:
    """获取全局 logger 实例（惰性初始化，线程安全）。"""
    global _logger
    if _logger is None:
        _logger = JokerLogger(log_dir)
    return _logger


def reset_logger() -> None:
    """重置 logger（主要用于测试）。"""
    global _logger
    _logger = None
