"""麦克风采集音频模块"""

import queue

import numpy as np
import sounddevice as sd


class AudioCapture:
    """从默认麦克风采集音频，每100ms输出一个numpy的chunk"""

    def __init__(
        self,
        audio_queue: queue.Queue,
        sample_rate: int = 16000,
        block_size: float = 0.1,
    ) -> None:
        self.audio_queue = audio_queue
        self.sample_rate = sample_rate
        self.block_size = int(block_size * sample_rate)
        self._stream: sd.InputStream | None = None

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
        if status:
            print(f"[AudioCapture]{status}")
        try:
            self.audio_queue.put_nowait(indata.flatten())
        except queue.Full:
            # 丢弃旧数据，保证实时性
            print("[AudioCapture] audio_queue 满，丢弃音频块")
