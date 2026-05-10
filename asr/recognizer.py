"""ASR 引擎 — 组合 MicrophoneVAD + Provider，在独立线程中运行。"""
import queue
import threading
from collections.abc import Callable

import numpy as np

from asr.vad import MicrophoneVAD
from asr.base import ASRProvider
from asr.providers import create_provider
from core.events import SENTINEL
from core.config import load_config


class ASREngine:
    """ASR 引擎：从 audio_queue 消费音频 → VAD 切句 → Provider 识别 → text_queue。"""

    def __init__(
        self,
        audio_queue: queue.Queue,
        text_queue: queue.Queue,
        provider: ASRProvider,
        *,
        sample_rate: int = 16000,
        energy_threshold: float = 0.006,
        silence_duration: float = 0.8,
        pre_speech_duration: float = 0.3,
        min_utterance_duration: float = 0.5,
    ) -> None:
        self.audio_queue = audio_queue
        self.text_queue = text_queue
        self.provider = provider

        self.vad = MicrophoneVAD(
            sample_rate=sample_rate,
            energy_threshold=energy_threshold,
            silence_duration=silence_duration,
            pre_speech_duration=pre_speech_duration,
            min_utterance_duration=min_utterance_duration,
        )

        self._thread: threading.Thread | None = None
        self._running = False

        self.on_speech_start: Callable | None = None
        self.on_speech_end: Callable | None = None

    @property
    def sample_rate(self) -> int:
        return self.provider.sample_rate

    @classmethod
    def from_config(
        cls, audio_queue: queue.Queue, text_queue: queue.Queue
    ) -> "ASREngine":
        config = load_config()["asr"]
        provider = create_provider(config)
        return cls(
            audio_queue,
            text_queue,
            provider,
            sample_rate=config.get("sample_rate", 16000),
            energy_threshold=config.get("energy_threshold", 0.006),
            silence_duration=config.get("silence_duration", 0.8),
            pre_speech_duration=config.get("pre_speech_duration", 0.3),
            min_utterance_duration=config.get("min_utterance_duration", 0.5),
        )

    def start(self) -> None:
        self.provider.setup()
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        self.audio_queue.put(SENTINEL)
        if self._thread is not None:
            self._thread.join(timeout=3.0)

    def reset_vad(self) -> None:
        self.vad.reset()

    def _run(self) -> None:
        while self._running:
            try:
                chunk = self.audio_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            if chunk is SENTINEL:
                break

            speech, just_started = self.vad.process(chunk)
            if just_started and self.on_speech_start:
                self.on_speech_start()
            if speech is not None:
                self._transcribe_and_emit(speech)
                if self.on_speech_end:
                    self.on_speech_end()

        # 退出前处理最后半句话
        speech = self.vad.flush()
        if speech is not None:
            self._transcribe_and_emit(speech)

    def _transcribe_and_emit(self, speech: np.ndarray) -> None:
        try:
            text = self.provider.transcribe(speech)
            if text:
                print(f"[ASR] {text}")
                self.text_queue.put(text)
        except Exception as e:
            print(f"[ASR] 模型推理失败: {e}")
