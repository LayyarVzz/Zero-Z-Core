"""麦克风采集音频模块 — 支持 RMS 打断检测。"""
import queue
from collections.abc import Callable

import numpy as np
import sounddevice as sd


class AudioCapture:
    """从默认麦克风采集音频，每 100ms 输出一个 numpy chunk。
    同时做本地 RMS 能量检测，用于打断 TTS 播放。
    """

    def __init__(
        self,
        audio_queue: queue.Queue,
        sample_rate: int = 16000,
        block_size: float = 0.1,
        rms_threshold: float = 0.02,
    ) -> None:
        self.audio_queue = audio_queue
        self.sample_rate = sample_rate
        self.block_size = int(block_size * sample_rate)
        self.rms_threshold = rms_threshold
        self._stream: sd.InputStream | None = None
        self.on_speech_detected: Callable | None = None
    def start(self) -> None:
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            blocksize=self.block_size,
            channels=1,
            callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def _callback(self, indata: np.ndarray, frames: int, time, status) -> None:
        chunk = indata.flatten()
        try:
            self.audio_queue.put_nowait(chunk)
        except queue.Full:
            pass

        # RMS 本地打断检测
        rms = float(np.sqrt(np.mean(chunk.astype(np.float64) ** 2)))
        if rms > self.rms_threshold and self.on_speech_detected is not None:
            self.on_speech_detected()
