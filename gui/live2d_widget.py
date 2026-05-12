"""Live2D 渲染组件 — QOpenGLWidget + live2d-py 封装。"""

import ctypes
import os
import traceback

import live2d.v3 as live2d
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtCore import Qt, QPoint

# 全局初始化 Cubism Core（必须在使用任何 LAppModel 之前调用）
live2d.init()

# OpenGL 函数指针
_glClearColor = ctypes.windll.opengl32.glClearColor
_glClearColor.restype = None
_glClearColor.argtypes = [ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float]

_glReadPixels = ctypes.windll.opengl32.glReadPixels
_glReadPixels.restype = None
_glReadPixels.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                          ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p]

GL_RGBA = 0x1908
GL_UNSIGNED_BYTE = 0x1401


def _clear_color_transparent() -> None:
    _glClearColor(0.0, 0.0, 0.0, 0.0)


class Live2DWidget(QOpenGLWidget):
    """在 QOpenGLWidget 中渲染 Live2D 模型，30FPS 更新，支持鼠标交互。"""

    def __init__(self, model_path: str, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_AlwaysStackOnTop)
        self.setAutoFillBackground(False)

        self._model_path = model_path
        self._model: live2d.LAppModel | None = None
        self._drag_offset = QPoint()
        self._initialized = False
        self._w = 0
        self._h = 0

    def initializeGL(self) -> None:
        try:
            self._init_impl()
        except Exception as e:
            print(f"[Live2DWidget] initializeGL 失败: {e}")
            traceback.print_exc()

    def _init_impl(self) -> None:
        self.makeCurrent()
        _clear_color_transparent()

        _saved_fd = os.dup(1)
        null_fd = os.open(os.devnull, os.O_WRONLY)
        os.dup2(null_fd, 1)
        os.close(null_fd)
        try:
            live2d.glInit()
            self._model = live2d.LAppModel()
            if not os.path.exists(self._model_path):
                os.dup2(_saved_fd, 1)
                os.close(_saved_fd)
                raise FileNotFoundError(f"Live2D 模型文件不存在: {self._model_path}")
            self._model.LoadModelJson(self._model_path)
        finally:
            os.dup2(_saved_fd, 1)
            os.close(_saved_fd)
        self._model.Resize(self.width(), self.height())
        self._model.SetAutoBlinkEnable(True)
        self._model.SetAutoBreathEnable(True)
        self.startTimer(int(1000 / 30))
        self._initialized = True

    def resizeGL(self, w: int, h: int) -> None:
        if self._model is not None and self._initialized:
            self._model.Resize(w, h)
        self._w = w
        self._h = h

    def paintGL(self) -> None:
        _clear_color_transparent()
        live2d.clearBuffer()
        if self._model is not None:
            self._model.Update()
            self._model.Draw()

    def is_pixel_opaque(self, wx: int, wy: int) -> bool:
        """检查窗口坐标 (wx, wy) 处的模型像素是否不透明（按需读取单个像素 alpha）。"""
        w = self._w or self.width()
        h = self._h or self.height()
        if w < 2 or h < 2 or not self._initialized:
            return False
        if wx < 0 or wy < 0 or wx >= w or wy >= h:
            return False
        gl_y = h - wy - 1
        buf = (ctypes.c_ubyte * 4)()
        try:
            self.makeCurrent()
            _glReadPixels(wx, gl_y, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, buf)
            self.doneCurrent()
        except Exception:
            return False
        return buf[3] > 10

    def timerEvent(self, _event) -> None:
        self.update()

    def mousePressEvent(self, event) -> None:
        self._drag_offset = event.globalPosition().toPoint() - self.window().pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._model is not None:
            self._model.Drag(event.pos().x(), event.pos().y())
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.window().move(event.globalPosition().toPoint() - self._drag_offset)
        super().mouseMoveEvent(event)

    def set_expression(self, name: str) -> None:
        if self._model is not None:
            self._model.SetExpression(name)

    def set_mouth_open(self, value: float) -> None:
        if self._model is not None:
            self._model.SetParameterValue("ParamMouthOpenY", value)

    def set_breath(self, enable: bool) -> None:
        if self._model is not None:
            self._model.SetAutoBreathEnable(enable)

    def dispose(self) -> None:
        if self._model is not None:
            self._model = None
        live2d.dispose()
