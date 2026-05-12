"""TurnController — 一轮对话的生命周期控制策略。

从 Orchestrator 中抽离打断 / 非打断两种交互模式，各自内聚在子类中。
"""

import threading
import time
from abc import ABC, abstractmethod

from core.events import State


class TurnController(ABC):
    """抽象基类：定义一轮对话生命周期中的 5 个钩子。"""

    @abstractmethod
    def on_new_input(self, orch) -> None:
        """新语音到达时的处理。"""
        ...

    @abstractmethod
    def on_playback_done(self, orch) -> None:
        """TTS 播放完毕时的处理。"""
        ...

    @abstractmethod
    def before_dispatch(self, orch) -> None:
        """dispatch 循环开始前的等待（如等开场白播完）。"""
        ...

    @abstractmethod
    def after_dispatch(self, orch) -> None:
        """dispatch 写入 TTS 后的等待（如等播放完毕）。"""
        ...

    @abstractmethod
    def shutdown(self) -> None:
        """Orchestrator.stop() 调用此方法以解除 dispatch 循环的阻塞。"""
        ...


class InterruptTurnController(TurnController):
    """打断模式：新语音到达时立即取消当前播放和 LLM 请求。"""

    def on_new_input(self, orch) -> None:
        orch._active_gen += 1  # 先递增代际，所有旧 gen 的音频块立即失效
        orch.tts.cancel()
        orch.llm.cancel()
        orch._drain_audio_out_queue()
        orch._drain_response_queue()

    def on_playback_done(self, orch) -> None:
        orch.state_queue.put(State.IDLE)

    def before_dispatch(self, orch) -> None:
        pass

    def after_dispatch(self, orch) -> None:
        pass

    def shutdown(self) -> None:
        pass


class NonInterruptTurnController(TurnController):
    """非打断模式：一句话完整处理+播放完毕后才开始录下一段。"""

    def __init__(self) -> None:
        self._playback_done = threading.Event()
        self._greeting_done = threading.Event()

    def on_new_input(self, orch) -> None:
        orch._drain_audio_queue()
        orch.asr.reset_vad()
        orch._drain_text_queue()

    def on_playback_done(self, orch) -> None:
        orch.state_queue.put(State.IDLE)
        time.sleep(0.5)
        self._playback_done.set()
        self._greeting_done.set()

    def before_dispatch(self, orch) -> None:
        self._greeting_done.wait(timeout=30.0)

    def after_dispatch(self, orch) -> None:
        self._playback_done.clear()
        self._playback_done.wait(timeout=60.0)

    def shutdown(self) -> None:
        self._greeting_done.set()
        self._playback_done.set()
