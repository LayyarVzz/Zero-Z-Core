"""定义状态事件"""

from enum import Enum, auto

# 队列哨兵-终止信号
SENTINEL = object()

# 播放完毕信号
PLAYBACK_DONE = object()


class State(Enum):
    """定义 Bot 的状态。"""

    IDLE = auto()      # 空闲，等待用户说话
    LISTENING = auto()  # 正在聆听用户语音
    THINKING = auto()   # LLM 思考中
    SPEAKING = auto()   # TTS 播放中
