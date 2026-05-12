"""GUI 入口 — 创建 QApplication、Orchestrator、管道和主窗口。"""

import ctypes
import io
import sys
import traceback

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from core.config import load_config
from core.orchestrator import Orchestrator
from asr.audio_capture import AudioCapture
from gui.pet_window import PetWindow
from gui.tray import TrayIcon
from gui.state_bridge import StateBridge
from gui.audio_player import AudioPlayer
from gui.subtitle import Subtitle
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
            self.orch = Orchestrator()
            self.orch.start()
        finally:
            sys.stdout = _real_stdout

        print(f"[Zero-Z] 启动完成 (角色: {config['character']['name']})")

        self.window = PetWindow(
            model_path=gui_cfg.get("model_path", ""),
            width=gui_cfg.get("width", 400),
            height=gui_cfg.get("height", 600),
        )

        self.player = AudioPlayer(sample_rate=self.orch._sample_rate)

        self.subtitle = Subtitle(self.window)
        self.subtitle.setGeometry(0, 10, self.window.width(), 60)

        self.bridge = StateBridge(self.orch)
        self._setup_bridge()

        self.capture = AudioCapture(self.orch.audio_queue)
        self.capture.on_speech_detected = self.orch.cancel_current_turn
        self.capture.start()

        self.tray = TrayIcon(self.window)

        app = QApplication.instance()
        if app:
            app.aboutToQuit.connect(self.cleanup)

    def _setup_bridge(self) -> None:
        bridge = self.bridge
        player = self.player
        subtitle = self.subtitle
        live2d = self.window.live2d

        bridge.state_changed.connect(lambda s: print(f"[State] {s}"))
        bridge.state_changed.connect(lambda s: live2d.set_breath(s != State.SPEAKING))

        bridge.llm_text.connect(
            lambda text, partial: subtitle.append_text(text, partial)
        )

        bridge.asr_text.connect(lambda text: subtitle.clear_text())

        bridge.audio_chunk.connect(player.play_chunk)
        player.mouth_open_changed.connect(live2d.set_mouth_open)

        player.playback_finished.connect(lambda: live2d.set_mouth_open(0.0))

    def cleanup(self) -> None:
        self.capture.stop()
        self.player.stop()
        self.bridge.stop()
        self.orch.stop()


def run_gui() -> int:
    if sys.platform == "win32":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("zero.z.core")

    # 捕获所有未处理异常，避免 Qt 静默吞掉
    def _excepthook(cls, exc, tb):
        traceback.print_exception(cls, exc, tb)
        sys.exit(1)

    sys.excepthook = _excepthook

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    controller = AppController()
    controller.window.show()
    controller.tray.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(run_gui())
