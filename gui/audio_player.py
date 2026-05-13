"""音频播放器 — QAudioSink 播放 PCM + 口型同步驱动。"""
import numpy as np
from PySide6.QtMultimedia import QAudioSink, QAudioFormat, QtAudio
from PySide6.QtCore import QIODevice, QByteArray, Signal, QObject, QIODeviceBase


class _AudioBuffer(QIODevice):
    """内存中的音频数据源，供 QAudioSink 消费。"""

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)  # type: ignore[arg-type]
        self._buf = QByteArray()

    def write_data(self, data: bytes) -> None:
        self._buf.append(data)
        self.readyRead.emit()

    def readData(self, maxlen: int) -> bytes:
        size = min(maxlen, self._buf.size())
        result = self._buf.data()[:size]  # data() 返回 bytes
        self._buf.remove(0, size)
        return result

    def writeData(self, _data: bytes, _maxlen: int = 0) -> int:
        return 0

    def isSequential(self) -> bool:
        return True

    def bytesAvailable(self) -> int:
        return self._buf.size()

    def clear_buf(self) -> None:
        self._buf.clear()


class AudioPlayer(QObject):
    """消费 audio_out_queue（通过 StateBridge 信号驱动），QAudioSink 播放。"""

    mouth_open_changed = Signal(float)
    playback_started = Signal()
    playback_finished = Signal()

    def __init__(self, sample_rate: int = 32000, parent: QObject | None = None):
        super().__init__(parent)
        self._active_gen = 0

        fmt = QAudioFormat()
        fmt.setSampleRate(sample_rate)
        fmt.setChannelCount(1)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)

        self._sink = QAudioSink(fmt)
        self._buf = _AudioBuffer()
        self._buf.open(QIODeviceBase.OpenModeFlag.ReadOnly)

    def play_chunk(self, gen_id: int, _text: str, pcm: np.ndarray) -> None:
        if gen_id < self._active_gen:
            return
        self._active_gen = gen_id

        audio_bytes = pcm.astype(np.int16).tobytes()
        self._buf.write_data(audio_bytes)

        if self._sink.state() != QtAudio.State.ActiveState:
            self._sink.start(self._buf)
            self.playback_started.emit()

        self.set_mouth_from_audio(pcm)

    def set_mouth_from_audio(self, audio_frame: np.ndarray) -> None:
        if len(audio_frame) == 0:
            self.mouth_open_changed.emit(0.0)
            return
        rms = np.sqrt(np.mean(audio_frame.astype(np.float32) ** 2))
        mouth = min(1.0, max(0.0, rms * 3.0))
        self.mouth_open_changed.emit(mouth)

    def stop(self) -> None:
        self._sink.stop()
        self._buf.clear_buf()
        self._active_gen += 1

    def clear(self) -> None:
        self.stop()
        self.playback_finished.emit()
