"""对话展示面板 — 滚动聊天气泡列表。"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QLabel, QFrame


class ConversationPanel(QWidget):
    """显示用户和 AI 的对话，仿聊天气泡样式的滚动视图。

    每条消息为一个 QLabel，用户消息蓝色背景居左，
    AI 消息紫色背景居左（实际也是左对齐，靠颜色区分）。
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setMinimumWidth(280)
        self.setMaximumWidth(400)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 滚动区域，承载消息列表
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)  # 去掉边框，融入背景

        # 消息容器，使用 VBox 纵向排列，stretch 把所有消息推到顶部
        self.message_container = QWidget()
        self.message_layout = QVBoxLayout(self.message_container)
        self.message_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.message_layout.setSpacing(8)  # 消息间距
        self.message_layout.addStretch()   # 底部弹簧，消息少时不铺满

        self.scroll_area.setWidget(self.message_container)
        layout.addWidget(self.scroll_area)

    def add_user_message(self, text: str) -> None:
        """添加用户消息（蓝色气泡）。"""
        label = QLabel(
            f'<div style="color:#2d5aa0;font-weight:bold;margin-bottom:2px">你</div>'
            f'<div style="color:#1a1a1a">{text}</div>'
        )
        label.setWordWrap(True)
        label.setStyleSheet("background:#e8f0fe;border-radius:8px;padding:10px")
        self._insert_label(label)

    def add_ai_message(self, text: str) -> None:
        """添加 AI 消息（紫色气泡）。"""
        label = QLabel(
            f'<div style="color:#8b3a8b;font-weight:bold;margin-bottom:2px">小零</div>'
            f'<div style="color:#1a1a1a">{text}</div>'
        )
        label.setWordWrap(True)
        label.setStyleSheet("background:#f3e8ff;border-radius:8px;padding:10px")
        self._insert_label(label)

    def _insert_label(self, label: QLabel) -> None:
        """将消息标签插入布局尾部并自动滚动到底部。

        先移除旧的 stretch → 插入新消息 → 重新添加 stretch，
        stretch 始终在最底部，消息在它上面依次排列。
        """
        # 移除旧的底部弹簧（先验证最后一项确实是弹簧，避免误删消息标签）
        if self.message_layout.count():
            item = self.message_layout.itemAt(self.message_layout.count() - 1)
            if item and item.spacerItem():
                self.message_layout.takeAt(self.message_layout.count() - 1)
        self.message_layout.addWidget(label)
        # 重新添加底部弹簧
        self.message_layout.addStretch()
        # 滚动到最底部，最新消息始终可见
        self.scroll_area.verticalScrollBar().setValue(
            self.scroll_area.verticalScrollBar().maximum()
        )
