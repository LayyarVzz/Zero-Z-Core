"""PySide6 主窗口与 GUI 启动入口。"""

import queue

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QMainWindow, QHBoxLayout, QWidget, QApplication

from core.events import State
from gui.live2d_widget import Live2DWidget
from gui.conversation_panel import ConversationPanel


class DigitalHumanApp(QMainWindow):
    """虚拟数字人主窗口，左侧 Live2D 角色 + 右侧对话面板。

    通过 QTimer 轮询 display_queue 和 state_queue，
    将后端事件翻译为 UI 更新。
    """

    def __init__(
        self,
        display_queue: queue.Queue,
        state_queue: queue.Queue | None = None,
        title: str = "Zero-Z 虚拟数字人",
        width: int = 800,
        height: int = 600,
    ):
        super().__init__()
        self.display_queue = display_queue  # 消息展示队列，生产者是编排器
        self.state_queue = state_queue      # 状态同步队列（可选）

        self.setWindowTitle(title)
        self.resize(width, height)
        self.setMinimumSize(600, 400)

        # 水平布局：Live2D（左 3/5）+ 对话面板（右 2/5）
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.live2d = Live2DWidget()
        layout.addWidget(self.live2d, stretch=3)

        self.conversation = ConversationPanel()
        layout.addWidget(self.conversation, stretch=2)

        # 50ms 定时器轮询队列，将后端数据转到 UI 线程
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll_queues)
        self._timer.start(50)

        self._current_state = State.IDLE

    def _poll_queues(self) -> None:
        """每 50ms 触发一次：从队列取消息和状态，更新 UI。

        使用 get_nowait() 非阻塞读取，队列为空直接跳过。
        """
        # 展示队列：(msg_type, text)  如 ("user", "你好")
        try:
            msg_type, text = self.display_queue.get_nowait()
            if msg_type == "user":
                self.conversation.add_user_message(text)
            elif msg_type == "ai":
                self.conversation.add_ai_message(text)
        except queue.Empty:
            pass

        # 状态队列：编排器主动推的状态变更
        if self.state_queue is not None:
            try:
                state = self.state_queue.get_nowait()
                self._set_state(state)
            except queue.Empty:
                pass

    def _set_state(self, state: State) -> None:
        """更新角色动画状态，避免重复设置同一状态触发无谓重绘。"""
        if state != self._current_state:
            self._current_state = state
            self.live2d.set_state(state)

    def closeEvent(self, event) -> None:
        """窗口关闭时停止定时器，避免在销毁后继续触发回调。"""
        self._timer.stop()
        super().closeEvent(event)


def run_gui(
    display_queue: queue.Queue,
    state_queue: queue.Queue | None = None,
) -> None:
    """GUI 启动入口：创建 QApplication 和主窗口，进入事件循环。

    阻塞直到窗口关闭，应在主线程调用。
    """
    import sys

    app = QApplication(sys.argv)
    app.setStyle("Fusion")  # 跨平台一致的现代风格

    from core.config import load_config

    config = load_config()
    gui_cfg = config.get("gui", {})

    window = DigitalHumanApp(
        display_queue=display_queue,
        state_queue=state_queue,
        title=f"Zero-Z - {config.get('character', {}).get('name', '小零')}",
        width=gui_cfg.get("width", 800),
        height=gui_cfg.get("height", 600),
    )
    window.show()
    app.exec()  # 进入 Qt 事件循环，阻塞直到窗口关闭
