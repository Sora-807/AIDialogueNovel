"""全局 logger — 进程启动即写入 saves/{story_id}/run.log。

stderr: 换行保留，终端阅读友好。
run.log: 换行转义为 \\n，每条日志严格一行，grep 友好。
"""
import logging
import sys
from pathlib import Path

_loggers: dict[str, logging.Logger] = {}


class _OneLineFormatter(logging.Formatter):
    """将 message 内容中的 \\n 转义为字面量，确保每条日志只占一行。
    Handler 负责追加 EOL，formatter 只管转义。"""
    def format(self, record):
        msg = super().format(record)
        return msg.replace("\n", "\\n")


class _FlushingFileHandler(logging.FileHandler):
    """每次写入后强制 flush，避免进程崩溃时日志丢失。"""
    def emit(self, record):
        super().emit(record)
        self.flush()


# 确保 provider 等模块 logger 有 stderr 输出
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)-8s] %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stderr,
)


def get_logger(story_id: str = "") -> logging.Logger:
    """获取全局 logger。首次调用时初始化 handler。

    story_id 为空时用 ROOT 日志（不写文件，仅 stderr）。
    """
    key = story_id or "__root__"
    if key in _loggers:
        return _loggers[key]

    logger = logging.getLogger(f"ainovel.{key}")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    # stderr handler — 与 run.log 同步
    sh = logging.StreamHandler(sys.stderr)
    sh.setLevel(logging.DEBUG)
    sh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)-8s] %(message)s", "%H:%M:%S"))
    logger.addHandler(sh)

    if story_id:
        from src.config import save_dir
        log_path = save_dir(story_id) / "run.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        fh = _FlushingFileHandler(str(log_path), encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(_OneLineFormatter("%(asctime)s [%(levelname)-8s] %(message)s", "%H:%M:%S"))
        logger.addHandler(fh)

    _loggers[key] = logger
    return logger
