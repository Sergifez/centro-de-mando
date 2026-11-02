#!/usr/bin/python3
"""Centro de mando del portátil: panel lateral con categorías y ajustes en vivo."""
import json
import os
import sys
import time
import unicodedata

from PyQt6.QtCore import QPropertyAnimation, QRectF, Qt, QThread, QTimer, pyqtProperty, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QIcon, QKeySequence, QPainter, QShortcut
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import (QMessageBox, QAbstractButton, QApplication, QComboBox, QDialog, QFrame, QHBoxLayout,
                             QLabel, QLineEdit, QListWidget, QPlainTextEdit, QGridLayout, QListWidgetItem, QMainWindow, QPushButton,
                             QScrollArea, QSlider, QStackedWidget, QTableWidget, QTableWidgetItem,
                             QSystemTrayIcon, QMenu, QVBoxLayout, QWidget, QHeaderView)

import dash
import pages
import settings as cfg

CSS = """
* { font-family: 'Noto Sans','DejaVu Sans',sans-serif; font-size: 13px; color: #cfd6de; }
QMainWindow, QDialog { background: #0b0f14; }
QWidget#sidepanel { background: #10151f; border: 1px solid #1a2230; border-radius: 10px; }
QListWidget#side { background: transparent; border: none; outline: 0; padding: 4px; }
QListWidget#side::item { padding: 5px 12px; border-radius: 6px; margin: 1px 0; border-left: 3px solid transparent; }
QListWidget#side::item:selected { background: #142136; color: #ffffff; border-left: 3px solid #3aa8e0; }
QListWidget#side::item:hover:!selected { background: #131c2a; }
QLabel#brand { color: #e8eef3; font-weight: bold; font-size: 15px; letter-spacing: 1px; }
QLabel#logo { color: #3aa8e0; font-size: 20px; }
QLineEdit, QKeySequenceEdit { background: #0f141b; border: 1px solid #1f2a3a; border-radius: 6px; padding: 5px 8px; }
QLineEdit:focus { border: 1px solid #3aa8e0; }
QLineEdit#search { background: #0f141b; border: 1px solid #1a2230; border-radius: 8px; padding: 6px 12px; min-width: 260px; }
QLineEdit#search:focus { border: 1px solid #3aa8e0; }
QLabel#h1 { font-size: 20px; font-weight: bold; color: #f0f4f8; }
QLabel#muted { color: #7f8b99; font-size: 12px; }
QLabel#rowtitle { font-weight: bold; color: #e6ebf0; }
QLabel#stat { font-size: 22px; font-weight: bold; color: #3aa8e0; }
QLabel#log { font-size: 11px; color: #7f8b99; }
QFrame#card { background: #0d131b; border: 1px solid #172030; border-left: 3px solid #3aa8e0; border-radius: 8px; }
QFrame#card[risk="true"] { border-left: 3px solid #c0804f; }
QFrame#card[pending="true"] { border: 1px solid #e0b43a; border-left: 3px solid #e0b43a; }
QFrame#card[plain="true"] { border-left: 1px solid #172030; }
QFrame#card QLabel { background: transparent; }
QFrame#user { background: #0c1118; border: 1px solid #1a2230; border-radius: 8px; }
QFrame#user QLabel { background: transparent; }
QPushButton { background: #151d28; border: 1px solid #1f2a3a; border-radius: 6px; padding: 6px 14px; }
QPushButton:hover { background: #1b2635; border-color: #3aa8e0; }
QPushButton:disabled { color: #566; }
QPushButton#primary { background: #1d6fa8; color: white; border-color: #3aa8e0; }
QPushButton#primary:hover { background: #2583c4; }
QComboBox { background: #151d28; border: 1px solid #1f2a3a; border-radius: 6px; padding: 4px 10px; min-width: 130px; }
QComboBox QAbstractItemView { background: #151d28; selection-background-color: #1d6fa8; }
QSlider::groove:horizontal { height: 5px; background: #1a2230; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #3aa8e0; border-radius: 2px; }
QSlider::handle:horizontal { background: #3aa8e0; width: 14px; margin: -6px 0; border-radius: 7px; }
QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background: #0b0f14; }
QScrollBar:vertical { background: transparent; width: 8px; }
QScrollBar::handle:vertical { background: #243044; border-radius: 4px; min-height: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
QPlainTextEdit#console { background: #0f151c; border: 1px solid #1a2230; border-radius: 8px; color: #9fb3c8;
    font-family: 'DejaVu Sans Mono',monospace; font-size: 11px; padding: 4px; }
QListWidget { background: #0d131b; border: 1px solid #172030; border-radius: 8px; padding: 4px; }
QListWidget::item { padding: 3px 6px; }
QListWidget::item:selected { background: #142136; color: #ffffff; }
QListWidget::indicator { margin-right: 8px; width: 14px; height: 14px; border: 1px solid #3a4a60; border-radius: 3px; background: #0b0f14; }
QListWidget::indicator:checked { background: #3aa8e0; border-color: #3aa8e0; }
QTableWidget::item:selected { background: #142136; color: #ffffff; }
QTableWidget { background: #0d131b; border: 1px solid #172030; gridline-color: #172030; }
QHeaderView::section { background: #10151f; border: none; padding: 4px; }
"""


class Switch(QAbstractButton):
    def __init__(self):
        super().__init__()
        self.setCheckable(True)
        self.setFixedSize(46, 24)
        self._pos = 0.0
        self.anim = QPropertyAnimation(self, b"pos", self)
        self.anim.setDuration(120)
        self.toggled.connect(self._animate)

    def _animate(self, on):
        self.anim.stop()
        self.anim.setEndValue(1.0 if on else 0.0)
        self.anim.start()

    def set_checked_silent(self, on):
        self.blockSignals(True)
        self.setChecked(on)
        self.blockSignals(False)
        self._pos = 1.0 if on else 0.0
        self.update()

    def getpos(self):
        return self._pos

    def setpos(self, v):
        self._pos = v
        self.update()

    pos = pyqtProperty(float, getpos, setpos)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        off, on = QColor("#5d6a7c"), QColor("#3aa8e0")
        t = self._pos
        col = QColor(int(off.red() + (on.red() - off.red()) * t), int(off.green() + (on.green() - off.green()) * t),
                     int(off.blue() + (on.blue() - off.blue()) * t))
        if not self.isEnabled():
            col.setAlpha(110)
        p.setBrush(col)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(0, 2, 46, 20), 10, 10)
        p.setBrush(QColor("#061422"))
        p.drawEllipse(QRectF(2 + 22 * t, 3, 18, 18))


class Job(QThread):
    done = pyqtSignal(object)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        try:
            self.fn()
            self.done.emit(None)
        except Exception as e:
            self.done.emit(str(e))


class Row(QFrame):
    """Una fila: título + descripción a la izquierda, control a la derecha."""

    def __init__(self, s, win):
        super().__init__()
        self.s, self.win = s, win
        self.setObjectName("card")
        self.setProperty("risk", bool(s.root))
        self.setProperty("plain", s.kind == "button")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 11, 14, 11)
        outer.setSpacing(8)
        top = QHBoxLayout()
        txt = QVBoxLayout()
        txt.setSpacing(2)
        t = QLabel(s.title)
        t.setObjectName("rowtitle")
        d = QLabel(s.desc + ("  · pide contraseña" if s.root else ""))
        d.setObjectName("muted")
        d.setWordWrap(True)
        txt.addWidget(t)
        txt.addWidget(d)
        top.addLayout(txt, 1)
        outer.addLayout(top)
        self.value = None
        if s.kind == "toggle":
            self.w = Switch()
            self.w.toggled.connect(lambda v: self.commit(v))
            top.addWidget(self.w)
        elif s.kind == "choice":
            self.w = QComboBox()
            for k, label in s.options:
                self.w.addItem(label, k)
            self.w.activated.connect(lambda _i: self.commit(self.w.currentData()))
            top.addWidget(self.w)
        elif s.kind == "slider":
            self.w = QSlider(Qt.Orientation.Horizontal)
            self.w.setRange(*s.rng)
            self.lbl = QLabel()
            self.lbl.setMinimumWidth(70)
            self.lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.w.valueChanged.connect(lambda v: self.lbl.setText(s.display(v)))
            self.w.sliderReleased.connect(lambda: self.commit(self.w.value()))
            self.w.actionTriggered.connect(self._keyboard_step)
            bottom = QHBoxLayout()
            bottom.addWidget(self.w, 1)
            bottom.addWidget(self.lbl)
            outer.addLayout(bottom)
        else:
            self.w = QPushButton(s.label)
            self.w.clicked.connect(lambda: self.commit(None))
            top.addWidget(self.w)

    def _keyboard_step(self, _a):
        if not self.w.isSliderDown():
            QTimer.singleShot(0, lambda: self.commit(self.w.value()))

    def refresh(self):
        """Relee el valor real del sistema y lo muestra (o el pendiente, si lo hay)."""
        if self.s.kind == "button":
            return
        try:
            self.value = self.s.get()
        except Exception:
            self.w.setEnabled(False)
            return
        self.w.setEnabled(True)
        self.sync()

    def sync(self):
        """Muestra el valor pendiente si existe; si no, el real. No toca el sistema."""
        s = self.s
        if s.kind == "button" or self.value is None:
            return
        pending = s.id in self.win.pending
        v = self.win.pending[s.id] if pending else self.value
        if self.property("pending") != pending:
            self.setProperty("pending", pending)
            self.style().unpolish(self)
            self.style().polish(self)
        if s.kind == "toggle":
            self.w.set_checked_silent(bool(v))
        elif s.kind == "choice":
            i = self.w.findData(v)
            if i < 0:
                label = "Por defecto del sistema" if v == "" else str(v)
                self.w.addItem(label, v)
                i = self.w.count() - 1
            self.w.setCurrentIndex(i)
        else:
            self.w.blockSignals(True)
            self.w.setValue(int(v))
            self.w.blockSignals(False)
            self.lbl.setText(s.display(int(v)))

    def commit(self, v):
        if self.s.kind == "button":  # acciones puntuales: se ejecutan al momento
            self.w.setEnabled(False)
            self.win.run(lambda: self.s.apply(v), self.s.title,
                         after=lambda: self.w.setEnabled(True))
        else:
            self.win.stage(self.s, v, self.value)


class SettingsPage(QWidget):
    def __init__(self, name, items, win):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 16, 12, 6)
        self.title = QLabel(name)
        self.title.setObjectName("h1")
        self.sub = QLabel()
        self.sub.setObjectName("muted")
        outer.addWidget(self.title)
        outer.addWidget(self.sub)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        self.grid = QGridLayout(body)
        self.grid.setContentsMargins(0, 10, 10, 8)
        self.grid.setSpacing(10)
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1)
        self.rows = [Row(s, win) for s in items if s.available()]
        for r in self.rows:  # con padre desde el principio: sin padre se mostrarían como ventanas sueltas
            r.setParent(body)
            r.hide()
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)
        self.reflow(self.rows)

    def reflow(self, visible):
        for r in self.rows:
            self.grid.removeWidget(r)
            if r not in visible:
                r.hide()
        for i, r in enumerate(visible):
            self.grid.addWidget(r, i // 2, i % 2, Qt.AlignmentFlag.AlignTop)
            r.show()
        self.grid.setRowStretch(len(visible) // 2 + 1, 1)
        self.sub.setText(f"{len(visible)} ajustes")

    @staticmethod
    def _norm(text):
        text = unicodedata.normalize("NFD", text.lower())
        return "".join(c for c in text if not unicodedata.combining(c) and c not in "-_ ")

    def filter(self, text):
        t = self._norm(text)
        self.reflow([r for r in self.rows if t in self._norm(r.s.title + r.s.desc)])

    def refresh(self):
        for r in self.rows:
            r.refresh()


# ------------------------------------------------------------------- resumen
def _cpu_temp():
    best = None
    for d in os.listdir("/sys/class/hwmon"):
        base = f"/sys/class/hwmon/{d}"
        if cfg.read(base + "/name") == "coretemp":
            try:
                return int(cfg.read(base + "/temp1_input")) // 1000
            except ValueError:
                pass
    try:
        best = int(cfg.read("/sys/class/thermal/thermal_zone0/temp")) // 1000
    except ValueError:
        pass
    return best


def _battery():
    for d in sorted(os.listdir("/sys/class/power_supply")):
        if d.startswith("BAT"):
            b = f"/sys/class/power_supply/{d}/"
            return cfg.read(b + "capacity", "?") + "%", {"Charging": "Cargando", "Discharging": "Descargando",
                                                          "Full": "Completa"}.get(cfg.read(b + "status"), cfg.read(b + "status"))
    return "—", "Sin batería"


def _ram():
    m = {}
    for line in cfg.read("/proc/meminfo").splitlines():
        k, v = line.split(":", 1)
        m[k] = int(v.split()[0])
    used = m["MemTotal"] - m["MemAvailable"]
    return f"{used / 1048576:.1f} / {m['MemTotal'] / 1048576:.1f} GB"


def _uptime():
    s = int(float(cfg.read("/proc/uptime", "0 0").split()[0]))
    return f"{s // 3600} h {s % 3600 // 60} min"


def _cpu_times():
    f = cfg.read("/proc/stat").splitlines()[0].split()[1:]
    v = [int(x) for x in f]
    return sum(v), v[3] + v[4]  # total, idle+iowait


def _net_bytes():
    rx = tx = 0
    for line in cfg.read("/proc/net/dev").splitlines()[2:]:
        name, _, rest = line.partition(":")
        if name.strip() == "lo":
            continue
        c = rest.split()
        rx += int(c[0])
        tx += int(c[8])
    return rx, tx


def _ram_frac():
    m = {}
    for line in cfg.read("/proc/meminfo").splitlines():
        k, v = line.split(":", 1)
        m[k] = int(v.split()[0])
    return (m["MemTotal"] - m["MemAvailable"]) / m["MemTotal"] * 100


class Summary(QWidget):
    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 18, 28, 10)
        outer.setSpacing(10)
        h = QLabel("Resumen")
        h.setObjectName("h1")
        sub = QLabel(f"{cfg.read('/etc/hostname')} · {os.uname().release}")
        sub.setObjectName("muted")
        outer.addWidget(h)
        outer.addWidget(sub)
        # medidores
        row = QHBoxLayout()
        row.setSpacing(10)
        self.g_cpu = dash.Gauge("CPU")
        self.g_ram = dash.Gauge("Memoria")
        self.g_temp = dash.Gauge("Temperatura", unit=" °", maximum=100, warn=0.65, crit=0.8)
        self.g_bat = dash.Gauge("Batería", invert=True, warn=0.7, crit=0.85)
        for g in (self.g_cpu, self.g_ram, self.g_temp, self.g_bat):
            row.addWidget(g, 1)
        outer.addLayout(row, 3)
        # gráficas
        row = QHBoxLayout()
        row.setSpacing(10)
        self.c_load = dash.AreaChart("CPU y memoria", [("CPU", dash.BLUE), ("RAM", dash.PURPLE)])
        self.c_temp = dash.AreaChart("Temperatura", [("CPU", dash.YELLOW)], maximum=100, unit=" °")
        self.c_net = dash.AreaChart("Red", [("↓", dash.GREEN), ("↑", dash.BLUE)], maximum=50_000, unit="B/s",
                                    autoscale=True)
        for c in (self.c_load, self.c_temp, self.c_net):
            row.addWidget(c, 1)
        outer.addLayout(row, 3)
        # disco + datos sueltos
        row = QHBoxLayout()
        row.setSpacing(10)
        self.b_disk = dash.Bar("Disco /")
        row.addWidget(self.b_disk, 2)
        self.facts = QLabel()
        self.facts.setObjectName("muted")
        self.facts.setTextFormat(Qt.TextFormat.RichText)
        self.facts.setWordWrap(True)
        row.addWidget(self.facts, 3)
        outer.addLayout(row)
        self.alerts = QLabel()
        self.alerts.setWordWrap(True)
        self.alerts.setTextFormat(Qt.TextFormat.RichText)
        outer.addWidget(self.alerts)
        outer.addStretch(0)
        self._cpu_prev = self._net_prev = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)

    def showEvent(self, e):
        self._cpu_prev = self._net_prev = None
        self.refresh()
        self.timer.start(1000)

    def hideEvent(self, e):
        self.timer.stop()

    def refresh(self):
        import shutil
        cap, status = _battery()
        t = _cpu_temp()
        # CPU % por diferencia de contadores
        tot, idle = _cpu_times()
        cpu, first = 0.0, self._cpu_prev is None
        if self._cpu_prev:
            dt, di = tot - self._cpu_prev[0], idle - self._cpu_prev[1]
            cpu = 100 * (1 - di / dt) if dt > 0 else 0.0
        self._cpu_prev = (tot, idle)
        ram = _ram_frac()
        # red en B/s
        now = time.monotonic()
        rx, tx = _net_bytes()
        down = up = 0.0
        if self._net_prev:
            el = max(now - self._net_prev[0], 0.1)
            down, up = (rx - self._net_prev[1]) / el, (tx - self._net_prev[2]) / el
        self._net_prev = (now, rx, tx)
        freqs = [int(cfg.read(f)) for f in
                 [f"/sys/devices/system/cpu/cpu{i}/cpufreq/scaling_cur_freq" for i in range(os.cpu_count() or 1)]
                 if cfg.read(f).isdigit()]
        ghz = f"{sum(freqs) / len(freqs) / 1e6:.2f} GHz" if freqs else "—"
        self.g_cpu.set_value(cpu, ghz)
        self.g_ram.set_value(ram, _ram())
        self.g_temp.set_value(t, "caliente" if t and t >= 75 else "normal" if t else "")
        self.g_bat.set_value(int(cap.rstrip("%")) if cap.rstrip("%").isdigit() else None, status)
        if not first:  # el primer ciclo no tiene diferencia de contadores
            self.c_load.push(cpu, ram)
            self.c_net.push(down, up)
        self.c_temp.push(t or 0)
        du = shutil.disk_usage("/")
        self.b_disk.set_value(du.used / du.total, f"{du.used / 1e9:.0f} de {du.total / 1e9:.0f} GB")
        gov = cfg.read("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor", "—")
        bright = f"{cfg._brightness_get()}%" if cfg.have("brightnessctl") else "—"
        load = " ".join(cfg.read("/proc/loadavg").split()[:3])
        self.facts.setText(f"Gobernador <b>{gov}</b> · Brillo <b>{bright}</b> · Carga <b>{load}</b> · "
                           f"Encendido <b>{_uptime()}</b>")
        self.alerts.setText(self._alerts(cap, status, t))

    @staticmethod
    def _alerts(cap, status, temp):
        warn = []
        if temp is not None and temp >= 85:
            warn.append(f"CPU a {temp} °C: demasiado caliente. Cierra procesos pesados o baja el preset.")
        elif temp is not None and temp >= 75:
            warn.append(f"CPU a {temp} °C: temperatura alta.")
        if cap.rstrip("%").isdigit() and int(cap.rstrip("%")) <= 20 and status == "Descargando":
            warn.append(f"Batería al {cap} y descargando: conecta el cargador.")
        b = cfg.read("/sys/class/power_supply/BAT0/energy_full_design", "0")
        f = cfg.read("/sys/class/power_supply/BAT0/energy_full", "0")
        if b.isdigit() and f.isdigit() and int(b) and int(f) / int(b) < 0.5:
            warn.append(f"La batería está al {int(f) * 100 // int(b)} % de su capacidad original.")
        import shutil
        du = shutil.disk_usage("/")
        if du.used / du.total >= 0.9:
            warn.append(f"El disco raíz está al {du.used * 100 // du.total} %: libera espacio en «Disco».")
        if not warn:
            return '<span style="color:#5fb878">✓ Sin avisos.</span>'
        return "".join(f'<p style="color:#e0b43a">⚠ {w}</p>' for w in warn)


# -------------------------------------------------------------------- presets
class PreviewDialog(QDialog):
    def __init__(self, parent, name, rows):
        super().__init__(parent)
        self.setWindowTitle(f"Preset «{name}»")
        self.resize(560, 420)
        lay = QVBoxLayout(self)
        info = QLabel("Estos son los cambios que se aplicarán. Los marcados con (admin) piden contraseña.")
        info.setObjectName("muted")
        lay.addWidget(info)
        t = QTableWidget(len(rows), 3)
        t.setHorizontalHeaderLabels(["Ajuste", "Ahora", "Nuevo"])
        t.verticalHeader().hide()
        t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        for i, (title, old, new) in enumerate(rows):
            for j, txt in enumerate((title, old, new)):
                t.setItem(i, j, QTableWidgetItem(txt))
        lay.addWidget(t, 1)
        if not rows:
            lay.addWidget(QLabel("Ya está todo como indica este preset."))
        b = QHBoxLayout()
        b.addStretch(1)
        no = QPushButton("Cancelar")
        ok = QPushButton("Aplicar")
        ok.setObjectName("primary")
        ok.setEnabled(bool(rows))
        no.clicked.connect(self.reject)
        ok.clicked.connect(self.accept)
        b.addWidget(no)
        b.addWidget(ok)
        lay.addLayout(b)


class PresetsPage(QWidget):
    def __init__(self, items, win):
        super().__init__()
        self.items = {s.id: s for s in items}
        self.win = win
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 22, 28, 12)
        h = QLabel("Presets")
        h.setObjectName("h1")
        outer.addWidget(h)
        sub = QLabel("Perfiles que cambian varios ajustes a la vez. Verás la vista previa antes de aplicar.")
        sub.setObjectName("muted")
        outer.addWidget(sub)
        for pid, name, desc, vals in cfg.PRESETS:
            card = QFrame()
            card.setObjectName("card")
            row = QHBoxLayout(card)
            row.setContentsMargins(16, 14, 16, 14)
            col = QVBoxLayout()
            n = QLabel(name)
            n.setObjectName("rowtitle")
            d = QLabel(desc)
            d.setObjectName("muted")
            d.setWordWrap(True)
            col.addWidget(n)
            col.addWidget(d)
            row.addLayout(col, 1)
            btn = QPushButton("Vista previa…")
            btn.clicked.connect(lambda _c, nm=name, v=vals: self.preview(nm, v))
            row.addWidget(btn)
            outer.addWidget(card)
        self.revert = QPushButton("Revertir último preset")
        self.revert.clicked.connect(self.do_revert)
        outer.addWidget(self.revert, 0, Qt.AlignmentFlag.AlignLeft)
        outer.addStretch(1)

    def refresh(self):
        self.revert.setEnabled(os.path.exists(cfg.SNAP_FILE))

    def preview(self, name, vals):
        rows, changes, snap = [], {}, {}
        for id, new in vals.items():
            s = self.items.get(id)
            if not s or not s.available():
                continue
            try:
                cur = s.get()
            except Exception:
                continue
            if cur == new or (s.kind == "choice" and str(cur) == str(new)):
                continue
            rows.append((s.title + (" (admin)" if s.root else ""), s.display(cur), s.display(new)))
            changes[id], snap[id] = new, cur
        if PreviewDialog(self.win, name, rows).exec() != QDialog.DialogCode.Accepted:
            return
        os.makedirs(cfg.STATE_DIR, exist_ok=True)
        json.dump(snap, open(cfg.SNAP_FILE, "w"))
        self.win.run(lambda: cfg.apply_many(list(self.items.values()), changes),
                     f"Preset «{name}»", after=self.win.refresh_current)

    def do_revert(self):
        try:
            snap = json.load(open(cfg.SNAP_FILE))
        except (OSError, ValueError):
            return
        self.win.run(lambda: cfg.apply_many(list(self.items.values()), snap),
                     "Preset revertido", after=lambda: (os.remove(cfg.SNAP_FILE), self.win.refresh_current()))


# --------------------------------------------------------------------- ventana
class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Centro de mando")
        self.resize(1180, 700)
        self.jobs = []
        self.pending = {}
        items = self.items = cfg.build()
        root = QWidget()
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(8)
        # barra superior
        top = QHBoxLayout()
        logo = QLabel("◈")
        logo.setObjectName("logo")
        brand = QLabel("CENTRO DE MANDO")
        brand.setObjectName("brand")
        self.search = QLineEdit()
        self.search.setObjectName("search")
        self.search.setPlaceholderText("Buscar ajustes…   Ctrl K")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._search)
        QShortcut(QKeySequence("Ctrl+K"), self, activated=self.search.setFocus)
        top.addWidget(logo)
        top.addWidget(brand)
        top.addSpacing(40)
        top.addWidget(self.search)
        top.addStretch(1)
        self.discard_btn = QPushButton("Descartar")
        self.discard_btn.clicked.connect(self.discard)
        self.apply_btn = QPushButton("Aplicar cambios")
        self.apply_btn.setObjectName("primary")
        self.apply_btn.clicked.connect(self.apply_pending)
        top.addWidget(self.discard_btn)
        top.addWidget(self.apply_btn)
        v.addLayout(top)
        body = QHBoxLayout()
        body.setSpacing(10)
        v.addLayout(body, 1)
        # panel lateral
        panel = QWidget()
        panel.setObjectName("sidepanel")
        panel.setFixedWidth(210)
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(6, 6, 6, 8)
        self.side = QListWidget()
        self.side.setObjectName("side")
        pl.addWidget(self.side, 1)
        user = QFrame()
        user.setObjectName("user")
        ul = QVBoxLayout(user)
        ul.setContentsMargins(12, 8, 12, 8)
        ul.setSpacing(0)
        self.host = QLabel(cfg.read("/etc/hostname"))
        self.host.setObjectName("rowtitle")
        self.bat = QLabel()
        self.bat.setObjectName("muted")
        ul.addWidget(self.host)
        ul.addWidget(self.bat)
        pl.addWidget(user)
        body.addWidget(panel)
        # contenido + consola
        right = QVBoxLayout()
        right.setSpacing(8)
        self.stack = QStackedWidget()
        right.addWidget(self.stack, 1)
        self.status = QLabel("Listo")
        self.status.setObjectName("log")
        self.console = QPlainTextEdit()
        self.console.setObjectName("console")
        self.console.setReadOnly(True)
        self.console.setFixedHeight(84)
        self.console.setMaximumBlockCount(200)
        right.addWidget(self.status)
        right.addWidget(self.console)
        body.addLayout(right, 1)
        self.page_of = {}
        group = None
        for cid, name, grp, icon in cfg.CATEGORIES:
            if grp != group:
                group = grp
                if grp != "GENERAL":
                    hdr = QListWidgetItem(grp)
                    hdr.setFlags(Qt.ItemFlag.NoItemFlags)
                    hdr.setForeground(QColor("#4f5b6b"))
                    f = hdr.font()
                    f.setPointSize(8)
                    f.setBold(True)
                    hdr.setFont(f)
                    self.side.addItem(hdr)
            it = QListWidgetItem(f"  {icon}   {name}")
            it.setData(Qt.ItemDataRole.UserRole, cid)
            self.side.addItem(it)
            if cid == "resumen":
                page = Summary()
            elif cid == "presets":
                page = PresetsPage(items, self)
            elif cid in pages.PAGES:
                page = pages.PAGES[cid](self)
            else:
                page = SettingsPage(name, [s for s in items if s.cat == cid], self)
            self.stack.addWidget(page)
            self.page_of[cid] = page
        self.results = SettingsPage("Resultados", items, self)
        self.stack.addWidget(self.results)
        self.side.currentItemChanged.connect(self._select)
        self.side.setCurrentRow(1)
        self.tray = None
        self.tick = QTimer(self)
        self.tick.timeout.connect(self._battery)
        self.tick.start(5000)
        self._battery()
        self._update_buttons()
        self._quitting = False
        self._tray_setup()
        self.log("Centro de mando iniciado")

    # ------------------------------------------------------------- bandeja
    def _tray_setup(self):
        self.tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        menu = QMenu()
        a_open = QAction("Abrir Centro de mando", menu)
        a_open.triggered.connect(self.bring_up)
        a_sum = QAction("Ir al Resumen", menu)
        a_sum.triggered.connect(lambda: (self.side.setCurrentRow(0), self.bring_up()))
        a_quit = QAction("Salir", menu)
        a_quit.triggered.connect(self._quit)
        for a in (a_open, a_sum):
            menu.addAction(a)
        menu.addSeparator()
        menu.addAction(a_quit)
        self._tray_menu = menu  # referencia viva
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda r: self.toggle_visible() if r == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.show()
        self._tray_tip()

    def _tray_tip(self):
        if self.tray:
            cap, status = _battery()
            t = _cpu_temp()
            self.tray.setToolTip(f"Centro de mando\nBatería {cap} · {status}" + (f"\nCPU {t} °C" if t else ""))

    def bring_up(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def toggle_visible(self):
        if self.isVisible() and not self.isMinimized():
            self.hide()
        else:
            self.bring_up()

    def _quit(self):
        self._quitting = True
        self.close()
        self._quitting = False  # si se canceló por cambios pendientes, seguimos vivos

    def closeEvent(self, e):
        if self.tray and self.tray.isVisible() and not self._quitting:
            self.hide()  # con bandeja, la X solo oculta; «Salir» del menú cierra de verdad
            e.ignore()
            return
        if self.pending and QMessageBox.question(
                self, "Cambios sin aplicar",
                f"Hay {len(self.pending)} cambio(s) sin aplicar. ¿Salir y descartarlos?",
        ) != QMessageBox.StandardButton.Yes:
            e.ignore()
            return
        super().closeEvent(e)

    def _battery(self):
        cap, status = _battery()
        self.bat.setText(f"Batería {cap} · {status}")
        self._tray_tip()

    def _select(self, item, _prev):
        if not item:
            return
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        page = self.page_of[item.data(Qt.ItemDataRole.UserRole)]
        self.stack.setCurrentWidget(page)
        if hasattr(page, "refresh"):
            page.refresh()

    def _search(self, text):
        if not text.strip():
            item = self.side.currentItem()
            if item:
                self._select(item, None)
            return
        self.side.clearSelection()
        self.stack.setCurrentWidget(self.results)
        self.results.filter(text.strip())
        self.results.refresh()

    def all_rows(self):
        for page in list(self.page_of.values()) + [self.results]:
            yield from getattr(page, "rows", [])

    def stage(self, setting, value, current):
        if value == current:
            self.pending.pop(setting.id, None)
        else:
            self.pending[setting.id] = value
        for r in self.all_rows():
            if r.s.id == setting.id:
                r.sync()
        self._update_buttons()

    def _update_buttons(self):
        n = len(self.pending)
        self.apply_btn.setText(f"Aplicar cambios ({n})" if n else "Aplicar cambios")
        self.apply_btn.setEnabled(bool(n))
        self.discard_btn.setEnabled(bool(n))

    def _reload_rows(self):
        self.pending.clear()
        self._update_buttons()
        for r in self.all_rows():
            r.refresh()
        self.refresh_current()

    def discard(self):
        self.pending.clear()
        for r in self.all_rows():
            r.sync()
        self._update_buttons()
        self.log("Cambios descartados")

    def apply_pending(self):
        if not self.pending:
            return
        changes = dict(self.pending)
        by_id = {s.id: s for s in self.items}
        label = f"{len(changes)} cambio(s)"
        for id, v in changes.items():
            self.log(f"  · {by_id[id].title}: {by_id[id].display(v)}")
        self.apply_btn.setEnabled(False)
        self.discard_btn.setEnabled(False)
        self.run(lambda: cfg.apply_many(self.items, changes), label, after=self._reload_rows)

    def refresh_current(self):
        p = self.stack.currentWidget()
        if hasattr(p, "refresh"):
            p.refresh()

    def log(self, msg):
        self.console.appendPlainText(f"[{time.strftime('%H:%M:%S')}] {msg}")

    def run(self, fn, label, after=None):
        self.status.setText(f"Aplicando: {label}…")
        self.log(f"▶ {label}")
        job = Job(fn)
        self.jobs.append(job)

        def done(err):
            self.jobs.remove(job)
            if err:
                self.status.setText("Error")
                for line in err.splitlines():
                    self.log(f"  ✗ {line}")
            else:
                self.status.setText("Listo")
                self.log("  ✓ Aplicado")
            if after:
                after()
        job.done.connect(done)
        job.start()


def main():
    if "--apply" in sys.argv:  # para el autostart de Openbox: reaplica ajustes de sesión
        cfg.apply_saved()
        return
    app = QApplication(sys.argv)
    app.setStyleSheet(CSS)
    app.setWindowIcon(QIcon(os.path.join(cfg.HERE, "panel-portatil.svg")))
    # instancia única: si ya hay una (p. ej. en la bandeja), la traemos al frente y salimos
    sock = QLocalSocket()
    sock.connectToServer("panel-portatil")
    if sock.waitForConnected(300):
        sock.write(b"show")
        sock.waitForBytesWritten(300)
        return
    QLocalServer.removeServer("panel-portatil")
    server = QLocalServer()
    server.listen("panel-portatil")
    w = Window()
    server.newConnection.connect(lambda: (server.nextPendingConnection(), w.bring_up()))
    if "--tray" not in sys.argv or not w.tray:  # --tray: arrancar oculto en la bandeja
        w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
