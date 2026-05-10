"""ASR Provider 抽象基类。"""
from abc import ABC, abstractmethod
import numpy as np


class ASRProvider(ABC):
    """ASR 识别 Provider 接口。

    每个 Provider 负责一个具体的识别后端（本地模型或云端 API）。
    """

    @abstractmethod
    def setup(self) -> None:
        """一次性初始化：加载模型、预热等。"""
        ...

    @abstractmethod
    def transcribe(self, audio: np.ndarray) -> str:
        """对一段 PCM 音频做语音识别，返回文本。"""
        ...

    @property
    @abstractmethod
    def sample_rate(self) -> int:
        """该 Provider 需要的输入采样率。"""
        ...
