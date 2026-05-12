"""桌面宠物悬浮窗 — 透明无边框置顶窗口，仅 Live2D 模型区域接收鼠标事件。"""

import ctypes
from ctypes import wintypes

from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QApplication
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QSurfaceFormat

from gui.live2d_widget import Live2DWidget

# ── Windows API 常量 ─────────────────────────────────────
WM_NCHITTEST = 0x0084
HTTRANSPARENT = -1
HTCAPTION = 2

# MSG 结构体（用于 nativeEvent 中解析 lParam）
class _MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd",    wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam",  wintypes.WPARAM),
        ("lParam",  wintypes.LPARAM),
        ("time",    wintypes.DWORD),
        ("pt",      wintypes.POINT),
    ]

# MARGINS 结构体（DWM 用）
class _MARGINS(ctypes.Structure):
    _fields_ = [
        ("cxLeftWidth",    ctypes.c_int),
        ("cxRightWidth",   ctypes.c_int),
        ("cyTopHeight",    ctypes.c_int),
        ("cyBottomHeight", ctypes.c_int),
    ]


class PetWindow(QMainWindow):
    """透明无边框置顶窗口，承载 Live2D 渲染和字幕叠加层。"""

    def __init__(self, model_path: str, width: int = 400, height: int = 600):
        super().__init__()
        self.setWindowTitle("Zero-Z")
        self._width = width
        self._height = height

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        fmt = QSurfaceFormat()
        fmt.setAlphaBufferSize(8)
        QSurfaceFormat.setDefaultFormat(fmt)

        central = QWidget(self)
        central.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        self.live2d = Live2DWidget(model_path)
        self.live2d.setMinimumSize(width, height)
        layout.addWidget(self.live2d)

        self.resize(width, height)
        self._position_bottom_right()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._enable_dwm_glass()

    def _position_bottom_right(self) -> None:
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.move(
                geo.right() - self._width - 20,
                geo.bottom() - self._height - 20,
            )

    def _enable_dwm_glass(self) -> None:
        """DwmExtendFrameIntoClientArea(-1) → 消除窗口亚克力边缘，实现真正全透明。"""
        try:
            hwnd = int(self.winId())
            margins = _MARGINS(-1, -1, -1, -1)
            ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea(
                hwnd, ctypes.byref(margins)
            )
        except Exception:
            pass  # 非 Windows 或旧版系统静默跳过

    def nativeEvent(self, eventType, message) -> tuple[bool, int]:  # noqa: ARG002
        if bytes(eventType) == b"windows_generic_MSG" and message:
            msg = ctypes.cast(message, ctypes.POINTER(_MSG)).contents
            if msg.message == WM_NCHITTEST:
                pt_x = msg.lParam & 0xFFFF
                pt_y = (msg.lParam >> 16) & 0xFFFF
                widget_pt = self.live2d.mapFromGlobal(QPoint(pt_x, pt_y))
                if self.live2d.is_pixel_opaque(widget_pt.x(), widget_pt.y()):
                    return False, HTCAPTION
                else:
                    return False, HTTRANSPARENT
        return False, 0

    def toggle_visibility(self) -> None:
        if self.isVisible():
            self.hide()
        else:
            self.show()
