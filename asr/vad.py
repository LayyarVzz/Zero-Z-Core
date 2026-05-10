"""麦克风 VAD — 纯 RMS 能量检测切句，不依赖任何 ASR 模型。"""
import numpy as np


class MicrophoneVAD:
    """RMS 能量 VAD，从音频流中切出完整语音片段。

    纯信号处理，不持有任何回调——由调用方根据返回值自行决定通知逻辑。
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        energy_threshold: float = 0.006,
        silence_duration: float = 0.8,
        pre_speech_duration: float = 0.3,
        min_utterance_duration: float = 0.5,
        max_utterance_duration: float = 30.0,
    ) -> None:
        self.sample_rate = sample_rate
        self.energy_threshold = energy_threshold
        self.silence_samples = int(silence_duration * sample_rate)
        self.pre_speech_samples = int(pre_speech_duration * sample_rate)
        self.min_utterance_samples = int(min_utterance_duration * sample_rate)
        self.max_utterance_samples = int(max_utterance_duration * sample_rate)

        self._chunks: list[np.ndarray] = []
        self._total_samples = 0
        self._utterance_start = 0
        self._is_speaking = False
        self._silence_samples = 0

    def reset(self) -> None:
        """重置 VAD 状态，清空缓冲区。"""
        self._chunks = []
        self._total_samples = 0
        self._utterance_start = 0
        self._is_speaking = False
        self._silence_samples = 0

    def process(self, chunk: np.ndarray) -> tuple[np.ndarray | None, bool]:
        """处理一个音频块，返回 (完整语音片段 | None, 是否刚检测到开始说话)。"""
        chunk_len = len(chunk)
        self._chunks.append(chunk)
        self._total_samples += chunk_len

        just_started = False

        # 30 秒上限强制切句
        if self._total_samples > self.max_utterance_samples:
            return self._cut(), False

        rms = float(np.sqrt(np.mean(chunk.astype(np.float64) ** 2)))

        if rms > self.energy_threshold:
            if not self._is_speaking:
                self._is_speaking = True
                self._utterance_start = max(
                    0, self._total_samples - chunk_len - self.pre_speech_samples
                )
                just_started = True
            self._silence_samples = 0
        elif self._is_speaking:
            self._silence_samples += chunk_len
            if self._silence_samples >= self.silence_samples:
                return self._cut(), False

        return None, just_started

    def flush(self) -> np.ndarray | None:
        """线程退出时产出缓冲区剩余语音。"""
        if self._is_speaking:
            return self._cut()
        return None

    def _cut(self) -> np.ndarray | None:
        """截取一段语音，重置 VAD 状态，返回 PCM 数组。"""
        full = np.concatenate(self._chunks)
        utterance_end = (
            self._total_samples - self._silence_samples + int(0.1 * self.sample_rate)
        )
        speech = full[self._utterance_start : utterance_end]

        result = speech if len(speech) >= self.min_utterance_samples else None

        keep = min(self.pre_speech_samples, self._total_samples)
        tail = full[-keep:]
        self._chunks = [tail]
        self._total_samples = keep
        self._utterance_start = 0
        self._is_speaking = False
        self._silence_samples = 0

        return result
