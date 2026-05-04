"""Live2D 角色占位控件 — 根据机器人的状态驱动彩色呼吸圆动画。

当前版本为简单几何占位（圆形 + 眼睛 + 状态文字），
后续可替换为真正的 Live2D Cubism 模型渲染。
"""

import math

from PySide6.QtCore import Qt, QTimer, QElapsedTimer
from PySide6.QtGui import QPainter, QColor, QFont
from PySide6.QtOpenGLWidgets import QOpenGLWidget

from core.events import State


class Live2DWidget(QOpenGLWidget):
    """Live2D 角色显示区域，展示状态驱动的呼吸圆动画。

    四种状态各自对应不同颜色：
    - IDLE (绿)：待机，微弱的呼吸律动
    - LISTENING (蓝)：用户正在说话
    - THINKING (黄)：LLM 生成回复中
    - SPEAKING (红)：TTS 播放中
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(400, 500)
        self._state = State.IDLE
        self._anim_time = 0.0
        # 用真实时间驱动动画，避免系统负载导致动画变慢
        self._elapsed = QElapsedTimer()
        self._elapsed.start()
        # 33ms ≈ 30fps，驱动动画平滑过渡
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)

        # 状态 -> 颜色映射
        self._colors = {
            State.IDLE: QColor(160, 210, 160),   # 淡绿
            State.LISTENING: QColor(100, 150, 240),  # 淡蓝
            State.THINKING: QColor(240, 180, 80),    # 淡黄
            State.SPEAKING: QColor(240, 100, 120),   # 淡红
        }

        # 状态 -> 中文标签
        self._labels = {
            State.IDLE: "待机中...",
            State.LISTENING: "倾听中...",
            State.THINKING: "思考中...",
            State.SPEAKING: "说话中...",
        }

    def set_state(self, state: State) -> None:
        """外部调用，切换角色状态 -> 触发重绘。"""
        self._state = state
        self.update()

    def _tick(self) -> None:
        """定时器回调，用真实时间差驱动动画，避免帧率波动影响动画速度。"""
        self._anim_time += self._elapsed.elapsed() / 1000.0
        self._elapsed.restart()
        self.update()

    def paintGL(self) -> None:
        """QOpenGLWidget 的帧渲染入口，每帧重绘整个角色画面。"""
        painter = QPainter(self)
        # 抗锯齿，让圆和文字边缘平滑
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 背景
        painter.fillRect(self.rect(), QColor(30, 30, 40))

        # 呼吸动画：用 sin 波周期性缩放半径，制造呼吸/脉冲效果
        breath = math.sin(self._anim_time * 2.0) * 0.08 + 1.0
        base_radius = min(self.width(), self.height()) * 0.25
        radius = int(base_radius * breath)

        # 圆心（偏上，给下方文字留空间）
        cx = self.width() // 2
        cy = self.height() // 2 - 30

        # 外发光——半透明大圆，模拟光晕
        color = self._colors[self._state]
        glow = QColor(color.red(), color.green(), color.blue(), 40)
        painter.setBrush(glow)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(
            cx - radius - 30, cy - radius - 30, (radius + 30) * 2, (radius + 30) * 2
        )

        # 主体圆
        painter.setBrush(color)
        painter.drawEllipse(cx - radius, cy - radius, radius * 2, radius * 2)

        # 眼睛（两个小白点）
        painter.setBrush(QColor(255, 255, 255))
        eye_offset = radius // 3   # 眼睛离圆心的水平偏移
        eye_radius = radius // 6   # 眼睛半径
        painter.drawEllipse(
            cx - eye_offset - eye_radius,
            cy - eye_radius,
            eye_radius * 2,
            eye_radius * 2,
        )  # 左眼
        painter.drawEllipse(
            cx + eye_offset - eye_radius,
            cy - eye_radius,
            eye_radius * 2,
            eye_radius * 2,
        )  # 右眼

        # 状态文字（人物下方居中显示）
        painter.setPen(QColor(255, 255, 255))
        font = QFont("Microsoft YaHei", 14)
        painter.setFont(font)
        label = self._labels.get(self._state, "")
        painter.drawText(
            self.rect().adjusted(0, 0, 0, -cy - radius - 20),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
            label,
        )

        painter.end()
