"""TTS 模块抽象基类"""

from abc import ABC, abstractmethod
from typing import Generator


import numpy as np


class TTSProvider(ABC):
    """对接任何 TTS 引擎只需实现此接口。

    synthesize_stream — 流式合成（逐步产出音频块，降低首音延迟）
    synthesize        — 非流式合成（一次性返回完整音频数组）
    sample_rate       — 该 Provider 输出的 PCM 音频采样率（由模型决定，不可配置）
    setup             — 初始化回调（加载模型、预加载音色等，默认空实现）
    """

    def setup(self) -> None:
        """初始化/预热。子类可覆盖，不需要初始化的 Provider 无需实现。"""
        return

    def is_ready(self) -> bool:
        """检查 Provider 是否就绪（服务可达、模型已加载等）。

        子类覆写以实现各自的健康检查逻辑，默认返回 True。
        """
        return True

    def cancel(self) -> None:
        """取消当前正在进行的合成。子类可覆盖实现具体取消逻辑。"""
        return

    @property
    @abstractmethod
    def sample_rate(self) -> int:
        """输出音频的采样率（Hz），由具体模型硬编码，播放链路据此驱动声卡。"""
        ...

    @abstractmethod
    def synthesize_stream(self, text: str) -> Generator[np.ndarray, None, None]:
        """流式合成，返回 PCM int16 音频块生成器。"""
        ...

    @abstractmethod
    def synthesize(self, text: str) -> np.ndarray:
        """非流式合成，返回完整 PCM int16 数组。"""
        ...
