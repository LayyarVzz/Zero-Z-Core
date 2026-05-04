"""使用内部 VAD 的 ASR 识别器，在独立线程中运行。"""

import queue
import threading
from collections.abc import Callable

import numpy as np
from funasr import AutoModel

from core.events import SENTINEL


class ASR:
    """从 audio_queue 消费原始音频块，进行手动 VAD 切句，将完整句子文本发送到 text_queue。"""

    def __init__(
        self,
        audio_queue: queue.Queue,
        text_queue: queue.Queue,
        sample_rate: int = 16000,
        energy_threshold: float = 0.006,
        silence_duration: float = 0.5,
        pre_speech_duration: float = 0.3,
        min_utterance_duration: float = 0.5,
    ):
        # 音频输入队列（来自麦克风采集）
        self.audio_queue = audio_queue
        # 文本输出队列（发给下游消费者）
        self.text_queue = text_queue

        # 采样率
        self.sample_rate = sample_rate

        # 能量阈值，低于此值视为静音
        self.energy_threshold = energy_threshold
        # 静音持续多久算一句话结束（采样点数）
        self.silence_samples = int(silence_duration * sample_rate)
        # 说话开始前保留多少背景音频
        self.pre_speech_samples = int(pre_speech_duration * sample_rate)
        # 最短有效语音长度（太短丢弃）
        self.min_utterance_samples = int(min_utterance_duration * sample_rate)

        # 消费线程
        self._thread: threading.Thread | None = None
        self._running = False

        self._model: AutoModel | None = None

        # ---- VAD 状态（运行时动态变化） ----
        # 音频块列表（攒 chunk，切句时才拼接，避免每次 concatenate 复制全量数据）
        self._chunks: list[np.ndarray] = []
        self._total_samples = 0  # 缓冲区总采样点数（缓存 len，避免反复 sum）
        # 当前语句在缓冲区中的起始位置
        self._utterance_start = 0
        # 是否正在说话
        self._is_speaking = False
        # 已连续静音的采样点数
        self._silence_samples = 0

        # ---- 回调钩子（外部可挂自定义行为） ----
        # 检测到开始说话时触发
        self.on_speech_start: Callable | None = None
        # 一句话结束时触发
        self.on_speech_end: Callable | None = None

    def reset_vad(self) -> None:
        """重置 VAD 状态，清空缓冲区。非打断模式停麦时调用，防止新旧语音混合。"""
        self._chunks = []
        self._total_samples = 0
        self._utterance_start = 0
        self._is_speaking = False
        self._silence_samples = 0

    def start(self) -> None:
        """启动识别：加载模型，开启消费线程。"""
        self._load_model()
        self._running = True
        # daemon=True：主线程退出时子线程自动终止，不会阻止进程退出
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """停止识别：通知线程退出，等待线程结束。"""
        self._running = False
        self.audio_queue.put(SENTINEL)  # 推入终止信号，让 get() 能返回
        if self._thread is not None:
            self._thread.join(timeout=3.0)  # 最多等 3 秒

    def _load_model(self) -> None:
        """加载 paraformer-zh 模型（含标点模型，不含 VAD——VAD 由手动逻辑处理）。"""
        self._model = AutoModel(
            model="paraformer-zh",
            vad_model="fsmn-vad",
            punc_model="ct-punc",
            disable_update=True,
        )

    def _run(self) -> None:
        """
        线程主循环：不断从 audio_queue 取音频块，
        交给 VAD 处理+识别，直到收到 SENTINEL 终止信号。
        """
        while self._running:
            try:
                chunk = self.audio_queue.get(timeout=0.1)  # 最多等 0.1s，避免死等
            except queue.Empty:
                # 没等到，回去检查 _running
                continue

            if chunk is SENTINEL:
                # 收到终止信号，退出循环
                break

            # VAD + 识别
            self._process_chunk(chunk)
        # 退出前处理最后半句话
        self._flush()

    def _process_chunk(self, chunk: np.ndarray) -> None:
        """
        对每个音频块做能量检测：
        - 能量超过阈值 -> 说话中，重置静音计数
        - 首次超过阈值 -> 标记说话开始，记录语句起点
        - 能量低于阈值 + 说话中 -> 累计静音样本，超时则切句识别
        """
        try:
            chunk_len = len(chunk)
            self._chunks.append(chunk)
            self._total_samples += chunk_len

            # 缓冲区超过 30 秒上限则强制切句，防止持续噪声导致内存无限增长
            if self._total_samples > int(30 * self.sample_rate):
                self._cut_utterance()
                return

            # 计算当前 chunk 的 RMS 能量（均方根）
            rms = float(np.sqrt(np.mean(chunk**2)))

            if rms > self.energy_threshold:
                # ---- 有声音 ----
                if not self._is_speaking:
                    self._is_speaking = True
                    self._utterance_start = max(
                        0, self._total_samples - chunk_len - self.pre_speech_samples
                    )
                    if self.on_speech_start:
                        self.on_speech_start()
                self._silence_samples = 0
            elif self._is_speaking:
                # ---- 正在说话但当前块是静音 ----
                self._silence_samples += chunk_len
                if self._silence_samples >= self.silence_samples:
                    self._cut_utterance()
        except Exception as e:
            print(f"[ASR] _process_chunk 异常: {e}，重置 VAD 状态")
            self.reset_vad()

    def _cut_utterance(self) -> None:
        """
        截取一段完整语音，送给模型识别。
        截取范围：从 utterance_start 到 当前静音起点 + 一小段余量。
        """
        # 只在切句时拼接一次，避免每个 chunk 都复制全量数据
        full = np.concatenate(self._chunks)

        # 语音结束点 = 缓冲区末尾 - 静音长度 + 0.1s 余量（避免尾音被截）
        utterance_end = (
            self._total_samples - self._silence_samples + int(0.1 * self.sample_rate)
        )
        speech = full[self._utterance_start : utterance_end]

        # 语音足够长才送识别
        if len(speech) >= self.min_utterance_samples and self._model is not None:
            try:
                result = self._model.generate(input=speech, batch_size_s=300)
                if result and result[0]["text"].strip():
                    text = result[0]["text"].strip()
                    print(f"[ASR] {text}")
                    self.text_queue.put(text)
            except Exception as e:
                print(f"[ASR] 模型推理失败: {e}")
            if self.on_speech_end:
                self.on_speech_end()

        # 保留缓冲区末尾一段（pre_speech_samples），作为下一句话的前置上下文
        keep = min(self.pre_speech_samples, self._total_samples)
        tail = full[-keep:]
        self._chunks = [tail]
        self._total_samples = keep

        # 重置 VAD 状态
        self._utterance_start = 0
        self._is_speaking = False
        self._silence_samples = 0

    def _flush(self) -> None:
        """
        线程退出时，如果还在说话中，把缓冲区剩余语音送识别。
        避免最后一句话被丢弃。
        """
        if self._is_speaking and self._model is not None:
            full = np.concatenate(self._chunks)
            speech = full[self._utterance_start :]
            if len(speech) >= self.min_utterance_samples:
                try:
                    result = self._model.generate(input=speech, batch_size_s=300)
                    if result and result[0]["text"].strip():
                        text = result[0]["text"].strip()
                        print(f"[ASR] {text}")
                        self.text_queue.put(text)
                except Exception as e:
                    print(f"[ASR] 模型推理失败: {e}")
