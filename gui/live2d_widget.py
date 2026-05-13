"""Live2D 渲染窗口 — QOpenGLWidget 直接作为桌面宠物悬浮窗。"""

import ctypes
import os
from ctypes import wintypes

import OpenGL.GL as gl

# 必须在 import live2d.v3 之前打补丁，否则 live2d 内部已缓存原始 Info
import live2d.utils.log as live2d_log
live2d_log.Info = lambda *args, **kwargs: None

import live2d.v3 as live2d
from PySide6.QtCore import QTimerEvent, Qt, QPoint
from PySide6.QtGui import QMouseEvent, QSurfaceFormat, QGuiApplication
from PySide6.QtOpenGLWidgets import QOpenGLWidget

live2d.init()

# ── Windows 鼠标穿透常量 ──────────────────────────────────
WM_NCHITTEST = 0x0084
HTTRANSPARENT = -1
HTCAPTION = 2


class _MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", wintypes.POINT),
    ]


class Live2DWidget(QOpenGLWidget):
    """Live2D 桌面宠物窗口。继承 QOpenGLWidget 直接作为顶层窗口。"""

    def __init__(self, model_path: str, width: int = 400, height: int = 600):
        super().__init__()

        self.setWindowTitle("Zero-Z")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        fmt = QSurfaceFormat()
        fmt.setAlphaBufferSize(8)
        QSurfaceFormat.setDefaultFormat(fmt)

        self._model_path = model_path
        self._model: live2d.LAppModel | None = None
        self._initialized = False
        self._w = width
        self._h = height
        self._click_in_model = False
        self._click_x = 0
        self._click_y = 0
        self._system_scale = QGuiApplication.primaryScreen().devicePixelRatio()

        self.resize(width, height)

    def initializeGL(self) -> None:
        live2d.glInit()

        if not os.path.exists(self._model_path):
            raise FileNotFoundError(f"Live2D 模型文件不存在: {self._model_path}")

        _saved = os.dup(1)
        _null = os.open(os.devnull, os.O_WRONLY)
        os.dup2(_null, 1)
        os.close(_null)
        try:
            self._model = live2d.LAppModel()
            self._model.LoadModelJson(self._model_path)
        finally:
            os.dup2(_saved, 1)
            os.close(_saved)

        model_name = os.path.basename(self._model_path).replace(".model3.json", "")
        print(f"[Live2D] 模型加载完成: {model_name}")

        self._model.Resize(self.width(), self.height())
        self._model.SetAutoBlinkEnable(True)
        self._model.SetAutoBreathEnable(True)

        self.startTimer(int(1000 / 60))
        self._initialized = True

    def resizeGL(self, w: int, h: int) -> None:
        if self._model is not None and self._initialized:
            self._model.Resize(w, h)
        self._w = w
        self._h = h

    def paintGL(self) -> None:
        live2d.clearBuffer()
        if self._model is not None:
            self._model.Update()
            self._model.Draw()

    def timerEvent(self, _: QTimerEvent | None) -> None:
        self.update()

    # ── 鼠标穿透 ──────────────────────────────────────────

    def nativeEvent(self, eventType, message) -> tuple[bool, int]:
        if eventType == b"windows_generic_MSG" and message:
            msg = ctypes.cast(message, ctypes.POINTER(_MSG)).contents
            if msg.message == WM_NCHITTEST:
                pt_x = msg.lParam & 0xFFFF
                pt_y = (msg.lParam >> 16) & 0xFFFF
                widget_pt = self.mapFromGlobal(QPoint(pt_x, pt_y))
                opaque = self._is_pixel_opaque(widget_pt.x(), widget_pt.y())
                print(f"[NCHITTEST] ({pt_x},{pt_y}) opaque={opaque}")
                if opaque:
                    return True, HTCAPTION
                else:
                    return True, HTTRANSPARENT
        return False, 0

    # ── 像素检测 ──────────────────────────────────────────

    def _is_pixel_opaque(self, wx: int, wy: int) -> bool:
        if not self._initialized:
            return False
        ratio = self._system_scale
        pw = int(wx * ratio)
        ph = int(wy * ratio)
        fw = int(self._w * ratio) if self._w else self.width()
        fh = int(self._h * ratio) if self._h else self.height()
        if pw < 0 or ph < 0 or pw >= fw or ph >= fh:
            return False
        gl_y = fh - ph - 1
        pixel = gl.glReadPixels(pw, gl_y, 1, 1, gl.GL_RGBA, gl.GL_UNSIGNED_BYTE)
        return pixel[3] > 10  # type: ignore[reportIndexIssue]

    # ── 鼠标交互 ──────────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent) -> None:
        x = event.scenePosition().x()
        y = event.scenePosition().y()
        if self._is_pixel_opaque(int(x), int(y)):
            self._click_in_model = True
            self._click_x = x
            self._click_y = y
        else:
            self._click_in_model = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._model is not None:
            gx = event.globalPosition().x() - self.x()
            gy = event.globalPosition().y() - self.y()
            self._model.Drag(int(gx), int(gy))
        if self._click_in_model:
            x = event.scenePosition().x()
            y = event.scenePosition().y()
            self.move(
                int(self.x() + x - self._click_x),
                int(self.y() + y - self._click_y),
            )
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._click_in_model = False
        super().mouseReleaseEvent(event)

    # ── 公共 API ──────────────────────────────────────────

    def set_expression(self, name: str) -> None:
        if self._model is not None:
            self._model.SetExpression(name)

    def set_mouth_open(self, value: float) -> None:
        if self._model is not None:
            self._model.SetParameterValue("ParamMouthOpenY", value)

    def set_breath(self, enable: bool) -> None:
        if self._model is not None:
            self._model.SetAutoBreathEnable(enable)

    def toggle_visibility(self) -> None:
        if self.isVisible():
            self.hide()
        else:
            self.show()
