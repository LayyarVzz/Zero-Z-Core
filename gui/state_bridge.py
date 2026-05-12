"""StateBridge — 管道线程队列 → GUI 主线程 Qt 信号桥接。

用 QTimer 轮询 Orchestrator 的各输出队列，发现新数据即发射信号。
Qt 信号跨线程安全：emit 在 StateBridge 所在线程（即主线程）的 event loop 中触发。
"""

import queue

from PySide6.QtCore import QObject, Signal, QTimer

from core.events import SENTINEL, PLAYBACK_DONE, State


class StateBridge(QObject):
    """轮询管道队列，发射 Qt 信号驱动 GUI 各组件。"""

    state_changed = Signal(State)
    llm_text = Signal(str, bool)
    asr_text = Signal(str)
    audio_chunk = Signal(int, str, object)
    playback_done = Signal()

    def __init__(self, orchestrator, parent=None):
        super().__init__(parent)
        self._orch = orchestrator

        self._state_timer = QTimer(self)
        self._state_timer.timeout.connect(self._poll_state)
        self._state_timer.start(50)

        self._display_timer = QTimer(self)
        self._display_timer.timeout.connect(self._poll_display)
        self._display_timer.start(50)

        self._audio_timer = QTimer(self)
        self._audio_timer.timeout.connect(self._poll_audio)
        self._audio_timer.start(30)

    def _poll_state(self) -> None:
        try:
            s = self._orch.state_queue.get_nowait()
            if s is SENTINEL:
                return
            self.state_changed.emit(s)
        except queue.Empty:
            return

    def _poll_display(self) -> None:
        while True:
            try:
                item = self._orch.display_queue.get_nowait()
                if item is SENTINEL:
                    return
                role, text = item
                if role == "user":
                    self.asr_text.emit(text)
                elif role == "ai":
                    self.llm_text.emit(text, False)
            except queue.Empty:
                return

    def _poll_audio(self) -> None:
        while True:
            try:
                item = self._orch.audio_out_queue.get_nowait()
                if item is SENTINEL:
                    return
                if item is PLAYBACK_DONE:
                    self.playback_done.emit()
                    continue
                if item is None:
                    continue
                gen_id, (text, pcm) = item
                self.audio_chunk.emit(gen_id, text, pcm)
            except queue.Empty:
                return

    def stop(self) -> None:
        self._state_timer.stop()
        self._display_timer.stop()
        self._audio_timer.stop()
