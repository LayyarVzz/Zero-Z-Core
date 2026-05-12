"""流式逐词字幕叠加层。"""

from PySide6.QtWidgets import QLabel
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import QGraphicsDropShadowEffect


class Subtitle(QLabel):
    """透明背景的逐词字幕，3 秒无新文本后自动隐藏。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)

        font = QFont("Microsoft YaHei", 16)
        font.setBold(True)
        self.setFont(font)
        self.setStyleSheet("color: white; background: transparent;")

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(6)
        shadow.setColor(QColor(0, 0, 0, 180))
        shadow.setOffset(0, 0)
        self.setGraphicsEffect(shadow)

        self.setMaximumHeight(80)
        self.setMinimumWidth(400)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)
        self._hide_timer.start(3000)

        self.hide()

    def append_text(self, text: str, is_partial: bool = True) -> None:
        current = self.text()
        self.setText(current + text)
        self.show()

        if not is_partial:
            self._hide_timer.start(3000)
        else:
            self._hide_timer.stop()

    def clear_text(self) -> None:
        self.clear()
        self.hide()
