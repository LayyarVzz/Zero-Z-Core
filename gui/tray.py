"""系统托盘图标和右键菜单。"""

from PySide6.QtWidgets import QSystemTrayIcon, QMenu, QApplication
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor
from PySide6.QtCore import Qt


def _make_tray_icon() -> QIcon:
    pixmap = QPixmap(16, 16)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(0, 200, 100))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(2, 2, 12, 12)
    painter.end()
    return QIcon(pixmap)


class TrayIcon(QSystemTrayIcon):
    def __init__(self, pet_window, parent=None):
        super().__init__(parent)
        self._pet_window = pet_window
        self._mouse_penetration = False
        self.setIcon(_make_tray_icon())
        self.setToolTip("Zero-Z")

        menu = QMenu()
        menu.addAction("显示/隐藏", self._pet_window.toggle_visibility)
        self._mouse_action = menu.addAction("鼠标穿透 (关)", self._toggle_mouse)
        menu.addSeparator()
        menu.addAction("退出", self._quit)

        self.setContextMenu(menu)

    def _toggle_mouse(self) -> None:
        self._mouse_penetration = not self._mouse_penetration
        self._pet_window.set_mouse_penetration(self._mouse_penetration)
        label = "鼠标穿透 (开)" if self._mouse_penetration else "鼠标穿透 (关)"
        self._mouse_action.setText(label)

    def _quit(self) -> None:
        self._pet_window.close()
        QApplication.quit()
