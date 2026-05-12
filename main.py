"""Zero-Z Virtual Digital Human — Application Entry Point."""
import logging
import os
import sys


# ── 压制第三方库冗余输出 ──────────────────────────────────
os.environ.setdefault("QT_LOGGING_RULES", "qt.multimedia.ffmpeg=false")

logging.basicConfig(level=logging.ERROR)
logging.getLogger("modelscope").setLevel(logging.ERROR)
logging.getLogger("jieba").setLevel(logging.WARNING)
logging.getLogger("funasr").setLevel(logging.WARNING)


def _mute_fd():
    """将 OS 文件描述符 1 (stdout) 重定向到 os.devnull，吞掉 C 扩展的 printf 输出。"""
    _mute_fd._saved = os.dup(1)
    null_fd = os.open(os.devnull, os.O_WRONLY)
    os.dup2(null_fd, 1)
    os.close(null_fd)


def _unmute_fd():
    """恢复 stdout 文件描述符。"""
    if hasattr(_mute_fd, "_saved"):
        os.dup2(_mute_fd._saved, 1)
        os.close(_mute_fd._saved)
        del _mute_fd._saved


# 导入阶段：压制 live2d-py、funasr、jieba 的所有输出（含 C 层 printf）
_mute_fd()
try:
    from gui.app import run_gui
    import jieba
    jieba.setLogLevel(60)
    jieba.initialize()
    # 禁用 FunASR 的 tqdm 进度条（写入 stderr）
    from tqdm import tqdm as _tqdm
    _tqdm.disable = True
except ImportError:
    pass
finally:
    _unmute_fd()


def main():
    run_gui()


if __name__ == "__main__":
    main()
