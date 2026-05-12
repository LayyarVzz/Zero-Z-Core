"""TTS 引擎 — 单 Provider，通过队列与外部通信。"""

import queue
import threading

from core.events import SENTINEL, PLAYBACK_DONE
from core.config import load_config
from tts.base import TTSProvider
from tts.providers import create_provider


class TTSEngine:
    """TTS 引擎，运行在独立线程中。

    从 tts_queue 消费文本，调用 Provider 合成音频，放入 audio_out_queue。
    """

    def __init__(
        self,
        tts_queue: queue.Queue,
        audio_out_queue: queue.Queue,
        provider: TTSProvider,
        *,
        stream_mode: bool = True,
    ) -> None:
        self.tts_queue = tts_queue  # 输入队列，消费待合成文本
        self.audio_out_queue = audio_out_queue  # 输出队列，产 PCM int16 音频块
        self.provider = provider
        self._thread: threading.Thread | None = None
        self._running = False
        # 流式模式：逐音频块产出；非流式：完整音频一次性产出
        self.stream_mode = stream_mode
        self._gen_id = 0  # 代际 ID，cancel() 时递增，旧代际 chunk 被丢弃

    @property
    def sample_rate(self) -> int:
        """播放采样率，直接读取 Provider 的输出采样率，无需单独配置。"""
        return self.provider.sample_rate

    def setup(self) -> None:
        """委托 Provider 执行一次性初始化（加载模型、预热音色等）。"""
        self.provider.setup()

    @classmethod
    def from_config(
        cls, tts_queue: queue.Queue, audio_out_queue: queue.Queue
    ) -> "TTSEngine":
        """工厂方法：从 config.yaml 读取 TTS 配置 -> 创建 Provider -> 构造引擎。"""
        config = load_config()["tts"]
        provider = create_provider(config)
        stream_mode = config.get("stream_mode", True)
        return cls(tts_queue, audio_out_queue, provider, stream_mode=stream_mode)

    def start(self) -> None:
        """启动后台线程。"""
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        """线程主循环：取文本 -> 合成 -> 产出音频块。"""
        while self._running:
            try:
                text = self.tts_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            if text is SENTINEL:
                break
            try:
                if self.stream_mode:
                    gen = self._gen_id
                    first = True
                    for chunk in self.provider.synthesize_stream(text):
                        if gen != self._gen_id:
                            break
                        chunk_text = text if first else ""
                        self.audio_out_queue.put((gen, (chunk_text, chunk)))
                        first = False
                    if gen == self._gen_id:
                        self.audio_out_queue.put(PLAYBACK_DONE)
                else:
                    audio = self.provider.synthesize(text)
                    self.audio_out_queue.put((self._gen_id, (text, audio)))
                    self.audio_out_queue.put(PLAYBACK_DONE)
            except Exception as e:
                print(f"[TTSEngine] TTS failed: {e}")
                self.audio_out_queue.put(PLAYBACK_DONE)

    def cancel(self) -> None:
        """取消当前正在进行的合成：递增代际 ID，旧代际 chunk 被丢弃。"""
        self._gen_id += 1
        self.provider.cancel()

    def stop(self) -> None:
        """协作式关闭：设标志位 -> 发 SENTINEL 唤醒阻塞的 get -> 等待线程退出。"""
        self._running = False
        self.tts_queue.put(SENTINEL)
        if self._thread is not None:
            self._thread.join(timeout=5.0)
