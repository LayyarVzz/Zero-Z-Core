"""GUI 入口 — 创建 QApplication、Orchestrator、管道和主窗口。"""

import atexit
import io
import os
import sys
import traceback

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QTimer

from core.config import load_config
from core.pipeline import Pipeline
from asr.audio_capture import AudioCapture
from gui.live2d_widget import Live2DWidget
from gui.tray import TrayIcon
from gui.state_bridge import StateBridge
from gui.audio_player import AudioPlayer
from core.events import State


class AppController:
    """应用程序总控制器，连接所有模块的生命周期。"""

    def __init__(self):
        config = load_config()
        gui_cfg = config.get("gui", {})

        # FunASR/modelscope 初始化时大量 print()，临时吞掉
        _real_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            self.orch = Pipeline()
            self.orch.start()
        finally:
            sys.stdout = _real_stdout

        print(f"[Zero-Z] 启动完成 (角色: {config['character']['name']})")

        self.window = Live2DWidget(
            model_path=gui_cfg.get("model_path", ""),
            width=gui_cfg.get("width", 400),
            height=gui_cfg.get("height", 600),
        )
        self._position_bottom_right()

        self.player = AudioPlayer(sample_rate=self.orch._sample_rate)

        self.bridge = StateBridge(self.orch)
        self._setup_bridge()

        self.capture = AudioCapture(self.orch.audio_queue)
        self.capture.on_speech_detected = self.orch.cancel_current_turn
        self.capture.start()

        self.tray = TrayIcon(self.window)

    def _position_bottom_right(self) -> None:
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.window.move(
                geo.right() - self.window.width() - 20,
                geo.bottom() - self.window.height() - 20,
            )

    def _setup_bridge(self) -> None:
        bridge = self.bridge
        player = self.player
        window = self.window

        bridge.state_changed.connect(lambda s: print(f"[State] {s}"))
        bridge.state_changed.connect(lambda s: window.set_breath(s != State.SPEAKING))

        bridge.audio_chunk.connect(player.play_chunk)
        bridge.playback_done.connect(
            lambda: self.orch._turn.on_playback_done(self.orch)
        )
        player.mouth_open_changed.connect(window.set_mouth_open)

        player.playback_started.connect(
            lambda: self.orch.state_queue.put(State.SPEAKING)
        )
        player.playback_finished.connect(lambda: window.set_mouth_open(0.0))

    def cleanup(self) -> None:
        self.capture.stop()
        self.player.stop()
        self.bridge.stop()
        self.orch.stop()
        print("[Zero-Z] 已退出")


def run_gui() -> int:
    # 进程退出前静音 C 扩展 printf（此时 Python print 已全部完成）
    def _silence_exit() -> None:
        try:
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, 1)
            os.dup2(devnull, 2)
            os.close(devnull)
        except OSError:
            pass
    atexit.register(_silence_exit)

    def _excepthook(cls, exc, tb):
        traceback.print_exception(cls, exc, tb)
        sys.exit(1)

    sys.excepthook = _excepthook

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    controller = AppController()
    controller.window.show()
    controller.tray.show()

    greeting = controller.orch.dialogue.get_greeting()
    if greeting:
        QTimer.singleShot(0, lambda: print(f"[LLM] {greeting}"))

    exit_code = app.exec()
    controller.cleanup()
    return exit_code


if __name__ == "__main__":
    sys.exit(run_gui())
