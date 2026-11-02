"""Widgets gráficos del Resumen: medidores circulares y gráficas de área con histórico."""
from collections import deque

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QSizePolicy, QWidget

BLUE, GREEN, YELLOW, RED, PURPLE = "#3aa8e0", "#5fb878", "#e0b43a", "#e0594f", "#a678e0"
TRACK, PANEL, BORDER, MUTED, TEXT = "#18212e", "#0d131b", "#172030", "#7f8b99", "#e6ebf0"


def level_color(frac, warn=0.7, crit=0.9, invert=False):
    """Verde → amarillo → rojo según la fracción (invert: bajo es malo, p. ej. batería)."""
    if invert:
        frac = 1 - frac
    return GREEN if frac < warn else YELLOW if frac < crit else RED


class Gauge(QWidget):
    """Medidor de arco con valor grande en el centro."""

    def __init__(self, title, unit="%", maximum=100.0, warn=0.7, crit=0.9, invert=False):
        super().__init__()
        self.title, self.unit, self.max = title, unit, maximum
        self.warn, self.crit, self.invert = warn, crit, invert
        self.value, self.shown, self.sub = None, 0.0, ""
        self.setMinimumSize(150, 170)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_value(self, v, sub=""):
        self.value, self.sub = v, sub
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.setPen(QPen(QColor(BORDER), 1))
        p.setBrush(QColor(PANEL))
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 10, 10)
        d = min(w - 36, h - 62)
        r = QRectF((w - d) / 2, 14, d, d)
        pen_w = max(9, d / 11)
        r = r.adjusted(pen_w / 2, pen_w / 2, -pen_w / 2, -pen_w / 2)
        # pista (arco de 270°, abierto por abajo)
        p.setPen(QPen(QColor(TRACK), pen_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawArc(r, 225 * 16, -270 * 16)
        frac = 0.0 if self.value is None else max(0.0, min(1.0, self.value / self.max))
        col = QColor(MUTED if self.value is None else level_color(frac, self.warn, self.crit, self.invert))
        if frac > 0:
            glow = QColor(col)
            glow.setAlpha(45)
            p.setPen(QPen(glow, pen_w + 7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawArc(r, 225 * 16, int(-270 * 16 * frac))
            p.setPen(QPen(col, pen_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawArc(r, 225 * 16, int(-270 * 16 * frac))
        # valor central
        f = QFont(self.font())
        f.setBold(True)
        f.setPixelSize(int(d / 4.2))
        p.setFont(f)
        p.setPen(QColor(TEXT))
        txt = "—" if self.value is None else f"{self.value:.0f}{self.unit}"
        p.drawText(QRectF(r.x(), r.y(), r.width(), r.height()), Qt.AlignmentFlag.AlignCenter, txt)
        # título y subtítulo
        f2 = QFont(self.font())
        f2.setPixelSize(13)
        f2.setBold(True)
        p.setFont(f2)
        p.setPen(QColor(TEXT))
        p.drawText(QRectF(0, h - 44, w, 20), Qt.AlignmentFlag.AlignCenter, self.title)
        f2.setBold(False)
        f2.setPixelSize(11)
        p.setFont(f2)
        p.setPen(QColor(MUTED))
        p.drawText(QRectF(4, h - 25, w - 8, 18), Qt.AlignmentFlag.AlignCenter, self.sub)


class AreaChart(QWidget):
    """Gráfica de áreas apiladas no, sino superpuestas, con histórico deslizante."""

    def __init__(self, title, series, maximum=100.0, unit="%", points=90, autoscale=False):
        """series: lista de (nombre, color). maximum: techo fijo, o mínimo si autoscale."""
        super().__init__()
        self.title, self.unit, self.max, self.auto = title, unit, maximum, autoscale
        self.series = [(n, QColor(c)) for n, c in series]
        self.data = [deque([0.0] * points, maxlen=points) for _ in series]
        self.points = points
        self.seeded = False
        self.setMinimumHeight(150)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def push(self, *values):
        if not self.seeded:  # primera lectura: rellena el histórico para no dibujar una subida desde 0
            self.seeded = True
            for dq, v in zip(self.data, values):
                dq.extend([float(v)] * self.points)
            self.update()
            return
        for dq, v in zip(self.data, values):
            dq.append(float(v))
        self.update()

    def _fmt(self, v):
        if self.unit == "B/s":
            for u, s in (("MB/s", 1e6), ("KB/s", 1e3)):
                if v >= s:
                    return f"{v / s:.1f} {u}"
            return f"{v:.0f} B/s"
        return f"{v:.0f}{self.unit}"

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.setPen(QPen(QColor(BORDER), 1))
        p.setBrush(QColor(PANEL))
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 10, 10)
        f = QFont(self.font())
        f.setPixelSize(13)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(TEXT))
        p.drawText(QRectF(14, 8, w / 2, 20), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.title)
        # leyenda con valor actual, alineada a la derecha
        f.setBold(False)
        f.setPixelSize(11)
        p.setFont(f)
        x = w - 14
        for (name, col), dq in reversed(list(zip(self.series, self.data))):
            label = f"{name} {self._fmt(dq[-1])}"
            tw = p.fontMetrics().horizontalAdvance(label)
            p.setPen(QColor(MUTED))
            p.drawText(QRectF(x - tw, 8, tw, 20), Qt.AlignmentFlag.AlignVCenter, label)
            p.setBrush(col)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(x - tw - 9, 18), 4, 4)
            x -= tw + 26
        top = max(self.max, max((max(dq) for dq in self.data), default=0) * 1.15) if self.auto else self.max
        gx, gy, gw, gh = 14, 36, w - 28, h - 36 - 12
        # rejilla
        p.setPen(QPen(QColor(TRACK), 1))
        for i in range(5):
            y = gy + gh * i / 4
            p.drawLine(QPointF(gx, y), QPointF(gx + gw, y))
        f.setPixelSize(10)
        p.setFont(f)
        p.setPen(QColor("#4a5666"))
        p.drawText(QRectF(gx + 3, gy + 1, 80, 14), Qt.AlignmentFlag.AlignLeft, self._fmt(top))
        step = gw / (self.points - 1)
        for (name, col), dq in zip(self.series, self.data):
            pts = [QPointF(gx + i * step, gy + gh - min(v / top, 1) * gh) for i, v in enumerate(dq)]
            line = QPainterPath(pts[0])
            for a, b in zip(pts, pts[1:]):  # curva suavizada
                mx = (a.x() + b.x()) / 2
                line.cubicTo(QPointF(mx, a.y()), QPointF(mx, b.y()), b)
            area = QPainterPath(line)
            area.lineTo(QPointF(gx + gw, gy + gh))
            area.lineTo(QPointF(gx, gy + gh))
            area.closeSubpath()
            g = QLinearGradient(0, gy, 0, gy + gh)
            c1, c2 = QColor(col), QColor(col)
            c1.setAlpha(110)
            c2.setAlpha(0)
            g.setColorAt(0, c1)
            g.setColorAt(1, c2)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(g)
            p.drawPath(area)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(col, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            p.drawPath(line)
            p.setBrush(col)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(pts[-1], 3.5, 3.5)


class Bar(QWidget):
    """Barra horizontal fina con etiqueta (disco, batería…)."""

    def __init__(self, title, warn=0.75, crit=0.9, invert=False):
        super().__init__()
        self.title, self.warn, self.crit, self.invert = title, warn, crit, invert
        self.frac, self.text = 0.0, ""
        self.setMinimumHeight(46)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_value(self, frac, text):
        self.frac, self.text = max(0.0, min(1.0, frac)), text
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.setPen(QPen(QColor(BORDER), 1))
        p.setBrush(QColor(PANEL))
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 10, 10)
        f = QFont(self.font())
        f.setPixelSize(12)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(TEXT))
        p.drawText(QRectF(14, 6, w / 2, 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.title)
        f.setBold(False)
        p.setFont(f)
        p.setPen(QColor(MUTED))
        p.drawText(QRectF(w / 2, 6, w / 2 - 14, 18), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                   self.text)
        track = QRectF(14, h - 16, w - 28, 7)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(TRACK))
        p.drawRoundedRect(track, 3.5, 3.5)
        if self.frac > 0:
            col = QColor(level_color(self.frac, self.warn, self.crit, self.invert))
            g = QLinearGradient(track.left(), 0, track.right(), 0)
            g.setColorAt(0, col.darker(140))
            g.setColorAt(1, col)
            p.setBrush(g)
            p.drawRoundedRect(QRectF(track.x(), track.y(), max(7, track.width() * self.frac), 7), 3.5, 3.5)
