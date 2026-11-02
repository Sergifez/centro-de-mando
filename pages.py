"""Páginas de información (no son ajustes): Batería, Procesos y Atajos."""
import glob
import os
import re
import shutil
import signal
import subprocess
import time
import xml.etree.ElementTree as ET

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import (QCheckBox, QDialog, QFormLayout, QFrame, QHBoxLayout, QHeaderView, QKeySequenceEdit,
                             QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QProgressBar,
                             QPushButton, QScrollArea, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

import deskcfg as dc
from settings import read, run_root, sh

CLK = os.sysconf("SC_CLK_TCK")
PAGE = os.sysconf("SC_PAGE_SIZE")


def _header(lay, title, sub=""):
    h = QLabel(title)
    h.setObjectName("h1")
    lay.addWidget(h)
    s = QLabel(sub)
    s.setObjectName("muted")
    s.setWordWrap(True)
    lay.addWidget(s)
    return s


class LivePage(QWidget):
    """Página que se refresca sola mientras está visible."""
    interval = 3000

    def __init__(self):
        super().__init__()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)

    def showEvent(self, e):
        self.refresh()
        self.timer.start(self.interval)

    def hideEvent(self, e):
        self.timer.stop()


# -------------------------------------------------------------------- batería
def _bat_dir():
    d = sorted(glob.glob("/sys/class/power_supply/BAT*"))
    return d[0] if d else None


def _num(base, name):
    try:
        return int(read(f"{base}/{name}", "0") or 0)
    except ValueError:
        return 0


class BatteryPage(LivePage):
    def __init__(self, win=None):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 16, 24, 8)
        _header(outer, "Batería", "Estado y desgaste de la batería, leído directamente del sistema.")
        self.tiles = {}
        names = ["Salud", "Carga", "Estado", "Capacidad actual", "Capacidad de fábrica", "Consumo",
                 "Autonomía estimada", "Voltaje", "Modelo"]
        grid = QVBoxLayout()
        grid.setSpacing(10)
        for i in range(0, len(names), 3):
            r = QHBoxLayout()
            r.setSpacing(10)
            for n in names[i:i + 3]:
                card = QFrame()
                card.setObjectName("card")
                card.setProperty("plain", True)
                v = QVBoxLayout(card)
                v.setContentsMargins(16, 12, 16, 12)
                lab = QLabel(n)
                lab.setObjectName("muted")
                val = QLabel("…")
                val.setObjectName("stat")
                v.addWidget(lab)
                v.addWidget(val)
                self.tiles[n] = val
                r.addWidget(card, 1)
            grid.addLayout(r)
        outer.addLayout(grid)
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.setObjectName("muted")
        outer.addWidget(self.note)
        outer.addStretch(1)

    def refresh(self):
        b = _bat_dir()
        if not b:
            self.note.setText("Este equipo no tiene batería.")
            return
        full, design, now = (_num(b, "energy_full"), _num(b, "energy_full_design"), _num(b, "energy_now"))
        power, volt = _num(b, "power_now"), _num(b, "voltage_now")
        status = read(f"{b}/status")
        health = full / design * 100 if design else 0
        wh = lambda x: f"{x / 1e6:.1f} Wh"
        if power > 0 and status == "Discharging":
            mins = now / power * 60
            eta = f"{int(mins // 60)} h {int(mins % 60):02d} min"
        elif power > 0 and status == "Charging":
            mins = (full - now) / power * 60
            eta = f"{int(mins // 60)} h {int(mins % 60):02d} min (hasta llenar)"
        else:
            eta = "—"
        vals = {
            "Salud": f"{health:.0f} %" if design else "—", "Carga": read(f"{b}/capacity") + " %",
            "Estado": {"Charging": "Cargando", "Discharging": "Descargando", "Full": "Completa",
                       "Not charging": "Sin cargar"}.get(status, status),
            "Capacidad actual": wh(full), "Capacidad de fábrica": wh(design),
            "Consumo": f"{power / 1e6:.1f} W" if power else "—", "Autonomía estimada": eta,
            "Voltaje": f"{volt / 1e6:.2f} V", "Modelo": read(f"{b}/model_name", "—"),
        }
        for k, v in vals.items():
            self.tiles[k].setText(v)
        if design and health < 50:
            self.note.setText(f"La batería conserva solo el {health:.0f} % de su capacidad original "
                              f"({wh(full)} de {wh(design)}). Es desgaste normal de una batería antigua: "
                              "bajar el brillo y usar el preset Ahorro alarga la autonomía, pero el límite lo "
                              "pone la propia celda. Este equipo no informa del número de ciclos.")
        elif design and health < 80:
            self.note.setText(f"Salud de la batería: {health:.0f} %. Tiene algo de desgaste.")
        else:
            self.note.setText(f"Salud de la batería: {health:.0f} %. En buen estado.")


# -------------------------------------------------------------------- procesos
def _sample():
    out = {}
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        try:
            raw = open(f"/proc/{d}/stat").read()
            f = raw[raw.rindex(")") + 2:].split()
            out[int(d)] = (int(f[11]) + int(f[12]), raw[raw.index("(") + 1:raw.rindex(")")],
                           os.stat(f"/proc/{d}").st_uid, int(f[21]) * PAGE)
        except (OSError, ValueError, IndexError):
            continue
    return out


class ProcessPage(LivePage):
    interval = 2500

    def __init__(self, win=None):
        super().__init__()
        self.prev, self.prev_t, self.by = {}, 0.0, "cpu"
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 16, 24, 8)
        self.sub = _header(outer, "Procesos", "Los que más consumen ahora mismo. Solo puedes cerrar los tuyos.")
        bar = QHBoxLayout()
        self.b_cpu, self.b_ram = QPushButton("Ordenar por CPU"), QPushButton("Ordenar por memoria")
        for b, k in ((self.b_cpu, "cpu"), (self.b_ram, "ram")):
            b.setCheckable(True)
            b.clicked.connect(lambda _c, k=k: self.sort_by(k))
        self.b_cpu.setChecked(True)
        self.b_term = QPushButton("Cerrar")
        self.b_kill = QPushButton("Forzar cierre")
        self.b_term.clicked.connect(lambda: self.signal_sel(signal.SIGTERM))
        self.b_kill.clicked.connect(lambda: self.signal_sel(signal.SIGKILL))
        for b in (self.b_cpu, self.b_ram):
            bar.addWidget(b)
        bar.addStretch(1)
        bar.addWidget(self.b_term)
        bar.addWidget(self.b_kill)
        outer.addLayout(bar)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["PID", "Proceso", "Usuario", "CPU %", "Memoria"])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for c in (0, 2, 3, 4):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        outer.addWidget(self.table, 1)
        self.users = {}

    def sort_by(self, k):
        self.by = k
        self.b_cpu.setChecked(k == "cpu")
        self.b_ram.setChecked(k == "ram")
        self.refresh()

    def _user(self, uid):
        if uid not in self.users:
            try:
                import pwd
                self.users[uid] = pwd.getpwuid(uid).pw_name
            except KeyError:
                self.users[uid] = str(uid)
        return self.users[uid]

    def refresh(self):
        now, cur = time.monotonic(), _sample()
        dt = now - self.prev_t if self.prev_t else 0
        rows = []
        for pid, (ticks, name, uid, rss) in cur.items():
            cpu = ((ticks - self.prev[pid][0]) / CLK / dt * 100) if dt and pid in self.prev else 0.0
            rows.append((pid, name, uid, cpu, rss))
        self.prev, self.prev_t = {p: v for p, v in cur.items()}, now
        rows.sort(key=lambda r: r[3] if self.by == "cpu" else r[4], reverse=True)
        rows = rows[:30]
        sel = self.selected_pid()
        self.table.setRowCount(len(rows))
        for i, (pid, name, uid, cpu, rss) in enumerate(rows):
            vals = [str(pid), name, self._user(uid), f"{cpu:.1f}", f"{rss / 1048576:.0f} MB"]
            for j, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if j in (0, 3, 4):
                    it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                it.setData(Qt.ItemDataRole.UserRole, (pid, uid))
                self.table.setItem(i, j, it)
            if pid == sel:
                self.table.selectRow(i)
        mem = {l.split(":")[0]: int(l.split()[1]) for l in read("/proc/meminfo").splitlines() if ":" in l}
        self.sub.setText(f"Memoria en uso: {(mem['MemTotal'] - mem['MemAvailable']) / 1048576:.1f} de "
                         f"{mem['MemTotal'] / 1048576:.1f} GB · {len(cur)} procesos. Solo puedes cerrar los tuyos.")

    def selected_pid(self):
        it = self.table.currentItem()
        return it.data(Qt.ItemDataRole.UserRole)[0] if it else None

    def signal_sel(self, sig):
        it = self.table.currentItem()
        if not it:
            return
        pid, uid = it.data(Qt.ItemDataRole.UserRole)
        name = self.table.item(it.row(), 1).text()
        if uid != os.getuid():
            QMessageBox.information(self, "Procesos", "Ese proceso pertenece a otro usuario.")
            return
        if pid == os.getpid():
            return
        if sig == signal.SIGKILL and QMessageBox.question(
                self, "Forzar cierre", f"¿Forzar el cierre de «{name}» ({pid})? Se perderá lo no guardado.",
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            os.kill(pid, sig)
        except OSError as e:
            QMessageBox.warning(self, "Procesos", str(e))
        QTimer.singleShot(600, self.refresh)


# --------------------------------------------------------------------- atajos
NS = "{http://openbox.org/3.4/rc}"
MODS = {"W": "Super", "C": "Ctrl", "A": "Alt", "S": "Mayús", "M": "Meta", "H": "Hyper"}


def pretty_key(k):
    parts = k.split("-")
    return " + ".join([MODS.get(p, p) for p in parts[:-1]] + [parts[-1]]) if len(parts) > 1 else k


def parse_keybinds():
    try:
        root = ET.parse(dc.RC_XML).getroot()
    except (OSError, ET.ParseError):
        return []
    out = []
    for kb in root.iter(NS + "keybind"):
        acts = []
        for a in kb.findall(NS + "action"):
            name = a.get("name", "")
            cmd = a.findtext(NS + "command") or a.findtext(NS + "execute")
            acts.append(f"Ejecutar: {' '.join(cmd.split())}" if cmd else
                        name + "".join(f" {c.text.strip()}" for c in a if c.text and c.text.strip()))
        out.append((pretty_key(kb.get("key", "")), " → ".join(acts), kb.get("key", "")))
    return out


QT_KEYS = {"Return": "Return", "Enter": "KP_Enter", "Esc": "Escape", "Del": "Delete", "Backspace": "BackSpace",
           "Space": "space", "Tab": "Tab", "Ins": "Insert", "PgUp": "Prior", "PgDown": "Next", "Print": "Print",
           "Left": "Left", "Right": "Right", "Up": "Up", "Down": "Down", "Home": "Home", "End": "End",
           "Backtab": "Tab"}


def qt_to_openbox(seq):
    """QKeySequence → cadena de tecla de Openbox ('W-C-t'); '' si no es válida."""
    if seq.isEmpty():
        return ""
    kc = seq[0]
    mods = kc.keyboardModifiers()
    key = QKeySequence(kc.key()).toString()
    if not key:
        return ""
    key = QT_KEYS.get(key, key.lower() if len(key) == 1 else key)
    pre = ""
    for flag, ch in ((Qt.KeyboardModifier.MetaModifier, "W"), (Qt.KeyboardModifier.ControlModifier, "C"),
                     (Qt.KeyboardModifier.AltModifier, "A"), (Qt.KeyboardModifier.ShiftModifier, "S")):
        if mods & flag:
            pre += ch + "-"
    return pre + key


def _esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def rc_change_key(old, new):
    txt = dc.read(dc.RC_XML)
    if re.search(rf'<keybind key="{re.escape(new)}"', txt):
        raise RuntimeError(f"{pretty_key(new)} ya está asignado")
    out, n = re.subn(rf'(<keybind key="){re.escape(old)}(")', lambda m: m.group(1) + _esc(new) + m.group(2), txt, count=1)
    if not n:
        raise RuntimeError("No encuentro ese atajo en rc.xml")
    dc.write(dc.RC_XML, out)
    dc.later("openbox")


def rc_delete_key(key):
    txt = dc.read(dc.RC_XML)
    out, n = re.subn(rf'[ \t]*<keybind key="{re.escape(key)}">.*?</keybind>[ \t]*\n?', "", txt, count=1, flags=re.S)
    if not n:
        raise RuntimeError("No encuentro ese atajo en rc.xml")
    dc.write(dc.RC_XML, out)
    dc.later("openbox")


def rc_add_key(key, command):
    txt = dc.read(dc.RC_XML)
    if re.search(rf'<keybind key="{re.escape(key)}"', txt):
        raise RuntimeError(f"{pretty_key(key)} ya está asignado")
    block = (f'    <keybind key="{_esc(key)}">\n      <action name="Execute">\n'
             f'        <command>{_esc(command)}</command>\n      </action>\n    </keybind>\n')
    i = txt.rfind("</keyboard>")
    if i < 0:
        raise RuntimeError("rc.xml no tiene sección <keyboard>")
    dc.write(dc.RC_XML, txt[:i].rstrip(" \t") + block + "  " + txt[i:])
    dc.later("openbox")


class KeyDialog(QDialog):
    """Pide una tecla (capturándola o escribiéndola) y, opcionalmente, un comando."""

    def __init__(self, parent, title, key="", with_command=False):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(460, 10)
        form = QFormLayout(self)
        self.cap = QKeySequenceEdit()
        self.cap.keySequenceChanged.connect(self._captured)
        form.addRow("Pulsa la combinación", self.cap)
        self.key = QLineEdit(key)
        self.key.setPlaceholderText("p. ej. W-e, C-A-t, XF86AudioMute")
        form.addRow("Tecla (Openbox)", self.key)
        self.cmd = QLineEdit()
        self.cmd.setPlaceholderText("p. ej. thunar")
        if with_command:
            form.addRow("Comando", self.cmd)
        note = QLabel("W = Super · C = Ctrl · A = Alt · S = Mayús")
        note.setObjectName("muted")
        form.addRow(note)
        row = QHBoxLayout()
        ok, no = QPushButton("Guardar"), QPushButton("Cancelar")
        ok.setObjectName("primary")
        ok.clicked.connect(self.accept)
        no.clicked.connect(self.reject)
        row.addStretch(1)
        row.addWidget(no)
        row.addWidget(ok)
        form.addRow(row)

    def _captured(self, seq):
        k = qt_to_openbox(seq)
        if k:
            self.key.setText(k)


class ShortcutsPage(QWidget):
    def __init__(self, win=None):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 16, 24, 8)
        self.sub = _header(outer, "Atajos de teclado", "Los de Openbox (rc.xml). Cada cambio hace copia de seguridad y recarga Openbox. La chuleta de conky es un archivo aparte y no se actualiza sola.")
        self.filter = QLineEdit()
        self.filter.setObjectName("search")
        self.filter.setPlaceholderText("Filtrar atajos o acciones…")
        self.filter.textChanged.connect(self.fill)
        outer.addWidget(self.filter)
        bar = QHBoxLayout()
        for text, fn in (("Añadir…", self.add), ("Cambiar tecla…", self.change), ("Eliminar", self.delete)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            bar.addWidget(b)
        bar.addStretch(1)
        outer.addLayout(bar)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Atajo", "Acción"])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        outer.addWidget(self.table, 1)
        self.binds, self.shown = [], []

    def refresh(self):
        self.binds = parse_keybinds()
        self.fill()

    def fill(self):
        q = self.filter.text().lower().strip()
        rows = [b for b in self.binds if q in (b[0] + " " + b[1]).lower()]
        self.table.setRowCount(len(rows))
        self.shown = rows
        for i, (k, a, raw) in enumerate(rows):
            self.table.setItem(i, 0, QTableWidgetItem(k))
            self.table.setItem(i, 1, QTableWidgetItem(a))
        self.sub.setText(f"{len(rows)} de {len(self.binds)} atajos · los cambios recargan Openbox al momento.")

    def _selected(self):
        r = self.table.currentRow()
        return self.shown[r] if 0 <= r < len(self.shown) else None

    def _do(self, fn, *args):
        try:
            dc.begin()
            fn(*args)
            dc.end()
        except Exception as e:
            dc._post.clear()
            dc._batch = 0
            QMessageBox.warning(self, "No se pudo", str(e))
        self.refresh()

    def add(self):
        d = KeyDialog(self, "Añadir atajo", with_command=True)
        if d.exec() and d.key.text().strip() and d.cmd.text().strip():
            self._do(rc_add_key, d.key.text().strip(), d.cmd.text().strip())

    def change(self):
        sel = self._selected()
        if not sel:
            QMessageBox.information(self, "Cambiar tecla", "Selecciona primero un atajo de la lista.")
            return
        d = KeyDialog(self, f"Nueva tecla para: {sel[1][:50]}", key=sel[2])
        if d.exec() and d.key.text().strip() and d.key.text().strip() != sel[2]:
            self._do(rc_change_key, sel[2], d.key.text().strip())

    def delete(self):
        sel = self._selected()
        if sel and QMessageBox.question(self, "Eliminar atajo", f"¿Eliminar {sel[0]}?\n{sel[1]}") == \
                QMessageBox.StandardButton.Yes:
            self._do(rc_delete_key, sel[2])


# ----------------------------------------------------------------------- disco
def _dir_size(path):
    total = 0
    for root, _dirs, files in os.walk(path, onerror=lambda e: None):
        for f in files:
            try:
                total += os.lstat(os.path.join(root, f)).st_size
            except OSError:
                pass
    return total


def _file_size(path):
    try:
        return os.lstat(path).st_size
    except OSError:
        return 0


def _mb(n):
    return f"{n / 1048576:.0f} MB" if n < 1 << 30 else f"{n / (1 << 30):.1f} GB"


def partitions():
    out = []
    for line in sh("df", "-P", "-B1", "-x", "tmpfs", "-x", "devtmpfs", "-x", "squashfs", "-x", "efivarfs").splitlines()[1:]:
        f = line.split()
        if len(f) >= 6 and f[0].startswith("/dev/"):
            out.append((f[5], f[0], int(f[2]), int(f[1])))
    return out


class DiskPage(LivePage):
    interval = 20000

    def __init__(self, win):
        super().__init__()
        self.win = win
        top = QVBoxLayout(self)
        top.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        scroll.setWidget(inner)
        top.addWidget(scroll)
        outer = QVBoxLayout(inner)
        outer.setContentsMargins(24, 16, 24, 8)
        _header(outer, "Disco y limpieza", "Espacio por partición y limpieza de archivos que se pueden regenerar.")
        self.parts = QVBoxLayout()
        self.parts.setSpacing(8)
        outer.addLayout(self.parts)
        title = QLabel("Limpieza")
        title.setObjectName("rowtitle")
        outer.addSpacing(6)
        outer.addWidget(title)
        self.apt = self._row(outer, "Caché de paquetes (apt)", "Paquetes .deb descargados. Se vuelven a bajar si hacen falta.",
                             "Limpiar", lambda: self.clean([["aptclean"]], "Limpiar caché de apt"))
        self.jr = self._row(outer, "Registros del sistema (journal)", "Reduce los logs de systemd a 100 MB.",
                            "Reducir", lambda: self.clean([["journal", 100]], "Reducir journal a 100 MB"))
        self.cache = self._row(outer, "Caché de usuario (~/.cache)", "Solo informativo: cada programa gestiona la suya.", None, None)
        self.cache_table = QTableWidget(0, 4)
        self.cache_table.setHorizontalHeaderLabels(["Programa", "", "Tamaño", ""])
        self.cache_table.verticalHeader().hide()
        self.cache_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.cache_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.cache_table.setShowGrid(False)
        hh = self.cache_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.cache_table.setMinimumHeight(25 * 30 + 30)
        self.cache_table.verticalHeader().setDefaultSectionSize(30)
        self.cache_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(self.cache_table, 1)
        self.busy = False

    def _row(self, outer, title, desc, btn, fn):
        card = QFrame()
        card.setObjectName("card")
        card.setProperty("risk", btn is not None)
        card.setProperty("plain", btn is None)
        lay = QHBoxLayout(card)
        lay.setContentsMargins(16, 10, 14, 10)
        col = QVBoxLayout()
        col.setSpacing(2)
        t = QLabel(title)
        t.setObjectName("rowtitle")
        d = QLabel(desc + ("  · pide contraseña" if btn else ""))
        d.setObjectName("muted")
        col.addWidget(t)
        col.addWidget(d)
        lay.addLayout(col, 1)
        size = QLabel("…")
        size.setObjectName("stat")
        size.setStyleSheet("font-size:16px;")
        lay.addWidget(size)
        if btn:
            b = QPushButton(btn)
            b.clicked.connect(fn)
            lay.addWidget(b)
        outer.addWidget(card)
        return size

    def clean(self, ops, label):
        self.win.run(lambda: run_root(ops), label, after=self.refresh)

    def refresh(self):
        while self.parts.count():
            w = self.parts.takeAt(0).widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        for mount, dev, used, total in partitions():
            card = QFrame()
            card.setObjectName("card")
            card.setProperty("plain", True)
            lay = QVBoxLayout(card)
            lay.setContentsMargins(16, 10, 16, 10)
            pct = used * 100 // total if total else 0
            head = QLabel(f"{mount}   ·   {dev}   ·   {_mb(used)} de {_mb(total)} ({pct} %)")
            head.setObjectName("rowtitle")
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(pct)
            bar.setTextVisible(False)
            bar.setFixedHeight(8)
            color = "#c0804f" if pct >= 90 else "#3aa8e0"
            bar.setStyleSheet(f"QProgressBar{{background:#1a2230;border:none;border-radius:4px;}}"
                              f"QProgressBar::chunk{{background:{color};border-radius:4px;}}")
            lay.addWidget(head)
            lay.addWidget(bar)
            self.parts.addWidget(card)
        self.apt.setText(_mb(_dir_size("/var/cache/apt/archives")))
        m = re.search(r"take up ([\d.]+)([KMG])", sh("journalctl", "--disk-usage"))
        self.jr.setText(f"{m.group(1)} {m.group(2)}B" if m else "—")
        if not self.busy:
            self._fill_cache()
        else:
            self.cache.setText("…")

    def _fill_cache(self):
        """Tamaño de cada programa dentro de ~/.cache, de mayor a menor."""
        base = os.path.expanduser("~/.cache")
        items = []
        try:
            names = os.listdir(base)
        except OSError:
            names = []
        for n in names:
            p = os.path.join(base, n)
            items.append((n, _dir_size(p) if os.path.isdir(p) and not os.path.islink(p) else _file_size(p)))
        items.sort(key=lambda x: -x[1])
        total = sum(sz for _n, sz in items)
        self.cache.setText(_mb(total))
        top = items[:25]
        biggest = max((sz for _n, sz in top), default=1) or 1
        self.cache_table.setRowCount(len(top))
        for i, (n, sz) in enumerate(top):
            self.cache_table.setItem(i, 0, QTableWidgetItem(n))
            cell = QWidget()
            cl = QVBoxLayout(cell)
            cl.setContentsMargins(8, 0, 8, 0)
            bar = QProgressBar()
            cl.addWidget(bar, 0, Qt.AlignmentFlag.AlignVCenter)
            bar.setRange(0, 1000)
            bar.setValue(int(sz * 1000 / biggest))
            bar.setTextVisible(False)
            bar.setFixedHeight(8)
            bar.setStyleSheet("QProgressBar{background:#1a2230;border:none;border-radius:4px;}"
                              "QProgressBar::chunk{background:#3aa8e0;border-radius:4px;}")
            self.cache_table.setCellWidget(i, 1, cell)
            it = QTableWidgetItem(f"{sz / 1024:.0f} KB" if sz < 1 << 20 else _mb(sz))
            it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.cache_table.setItem(i, 2, it)
            b = QPushButton("Borrar")
            b.setStyleSheet("padding:2px 10px;")
            b.clicked.connect(lambda _c=False, n=n, sz=sz: self.delete_cache(n, sz))
            self.cache_table.setCellWidget(i, 3, b)

    def delete_cache(self, name, size):
        base = os.path.realpath(os.path.expanduser("~/.cache"))
        path = os.path.join(base, name)
        if not name or "/" in name or name in (".", "..") or os.path.dirname(path) != base:
            return
        if QMessageBox.question(self, "Borrar caché", f"¿Borrar la caché de «{name}» ({_mb(size)})?\n\n"
                                "El programa la volverá a crear; puede tardar más en la próxima apertura. "
                                "Ciérralo antes si está abierto.") != QMessageBox.StandardButton.Yes:
            return

        def rm():
            if os.path.islink(path) or os.path.isfile(path):
                os.unlink(path)
            else:
                shutil.rmtree(path, ignore_errors=True)

        self.win.run(rm, f"Borrar caché de {name}", after=self.refresh)


# ------------------------------------------------------------- actualizaciones
def upgradable():
    out = []
    for line in sh("apt", "list", "--upgradable", timeout=30).splitlines():
        m = re.match(r"^(\S+?)/\S+ (\S+) \S+ \[.*?: (.+?)\]", line)
        if m:
            out.append((m.group(1), m.group(3), m.group(2)))
    return out


class UpdatesPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 16, 24, 8)
        self.sub = _header(outer, "Actualizaciones", "Paquetes de Debian pendientes de actualizar.")
        bar = QHBoxLayout()
        self.b_check = QPushButton("Buscar actualizaciones")
        self.b_check.clicked.connect(self.check)
        self.b_term = QPushButton("Actualizar en terminal")
        self.b_term.setObjectName("primary")
        self.b_term.clicked.connect(self.upgrade_terminal)
        bar.addWidget(self.b_check)
        bar.addStretch(1)
        bar.addWidget(self.b_term)
        outer.addLayout(bar)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Paquete", "Versión instalada", "Versión nueva"])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        outer.addWidget(self.table, 1)

    def check(self):
        self.win.run(lambda: run_root([["aptupdate"]]), "Buscar actualizaciones", after=self.refresh)

    def upgrade_terminal(self):
        # Se actualiza en una terminal visible para ver y confirmar lo que instala apt.
        subprocess.Popen(["x-terminal-emulator", "-e", "bash", "-c",
                          "sudo apt full-upgrade; echo; read -rp 'Terminado. Pulsa Intro…'"],
                         start_new_session=True)

    def refresh(self):
        rows = upgradable()
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            for j, v in enumerate(r):
                self.table.setItem(i, j, QTableWidgetItem(v))
        try:
            when = time.strftime("%d/%m/%Y %H:%M", time.localtime(os.stat("/var/lib/apt/lists").st_mtime))
        except OSError:
            when = "desconocida"
        n = len(rows)
        self.sub.setText((f"{n} paquete(s) pendientes" if n else "Todo al día") + f" · última búsqueda: {when}")
        self.b_term.setEnabled(n > 0)



# -------------------------------------------------------------------- dotfiles
DOTFILES = os.path.expanduser("~/dotfiles")
STATUS_ES = {"M": "modificado", "A": "añadido", "D": "borrado", "R": "renombrado", "?": "nuevo"}


def git(*args, timeout=30):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", LC_ALL="C")
    r = subprocess.run(["git", "-C", DOTFILES, *args], capture_output=True, text=True, timeout=timeout, env=env)
    return r.returncode, (r.stdout + r.stderr).rstrip()


class DotfilesPage(QWidget):
    """Estado del repo de dotfiles: elegir qué archivos van al commit y subirlos."""

    def __init__(self, win=None):
        super().__init__()
        self.win = win
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 16, 24, 8)
        self.sub = _header(outer, "Dotfiles", "Cambios pendientes de ~/dotfiles. Marca los que quieras incluir en el commit.")
        self.files = QListWidget()
        outer.addWidget(self.files, 3)
        self.msg = QLineEdit()
        self.msg.setObjectName("search")
        self.msg.setPlaceholderText("Mensaje del commit…")
        outer.addWidget(self.msg)
        bar = QHBoxLayout()
        self.b_commit = QPushButton("Commit de lo marcado")
        self.b_commit.setObjectName("primary")
        self.b_commit.clicked.connect(self.commit)
        self.b_push = QPushButton("Subir (push)")
        self.b_push.clicked.connect(self.push)
        b_ref = QPushButton("Actualizar")
        b_ref.clicked.connect(self.refresh)
        for b in (self.b_commit, self.b_push, b_ref):
            bar.addWidget(b)
        bar.addStretch(1)
        outer.addLayout(bar)
        self.info = QLabel()
        self.info.setObjectName("muted")
        self.info.setWordWrap(True)
        outer.addWidget(self.info)
        self.log_view = QListWidget()
        self.log_view.setMaximumHeight(110)
        outer.addWidget(self.log_view)

    def showEvent(self, e):
        self.refresh()

    def refresh(self):
        if not os.path.isdir(os.path.join(DOTFILES, ".git")):
            self.sub.setText("No hay repositorio en ~/dotfiles.")
            return
        self.files.clear()
        _, out = git("status", "--porcelain", "-uall")
        for line in out.splitlines():
            code, path = line[:2], line[3:].strip('"')
            it = QListWidgetItem(f"{STATUS_ES.get(code.strip()[:1], code)}  ·  {path}")
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Unchecked)
            it.setData(Qt.ItemDataRole.UserRole, path)
            self.files.addItem(it)
        n = self.files.count()
        _, branch = git("rev-parse", "--abbrev-ref", "HEAD")
        rc, ahead = git("rev-list", "--count", "@{u}..HEAD")
        ahead = ahead.strip()
        branch = branch.strip()
        pend = f" · {ahead} commit(s) sin subir" if rc == 0 and ahead != "0" else ""
        self.info.setText(f"Rama {branch}{pend}" + ("" if n else " · todo al día, sin cambios pendientes."))
        self.b_commit.setEnabled(n > 0)
        self.b_push.setEnabled(rc == 0 and ahead != "0")
        self.log_view.clear()
        _, hist = git("log", "-8", "--format=%h  %ad  %s", "--date=format:%d/%m %H:%M")
        self.log_view.addItems(hist.splitlines())

    def commit(self):
        paths = [self.files.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.files.count())
                 if self.files.item(i).checkState() == Qt.CheckState.Checked]
        msg = self.msg.text().strip()
        if not paths or not msg:
            QMessageBox.information(self, "Commit", "Marca al menos un archivo y escribe un mensaje.")
            return
        rc, out = git("add", "--", *paths)
        if rc == 0:
            rc, out = git("commit", "-m", msg, "--", *paths)
        if rc:
            QMessageBox.warning(self, "No se pudo hacer el commit", out)
        else:
            self.msg.clear()
            if self.win:
                self.win.log(f"✓ Commit en dotfiles: {msg}")
        self.refresh()

    def push(self):
        if QMessageBox.question(self, "Subir dotfiles", "¿Enviar los commits a GitHub (origin)?") != \
                QMessageBox.StandardButton.Yes:
            return
        try:
            rc, out = git("push", timeout=60)
        except subprocess.TimeoutExpired:
            rc, out = 1, "Tiempo agotado (¿faltan credenciales?)."
        if rc:
            QMessageBox.warning(self, "No se pudo subir", out)
        elif self.win:
            self.win.log("✓ Dotfiles subidos a origin")
        self.refresh()


PAGES = {"actualizaciones": UpdatesPage, "disco": DiskPage, "bateria": BatteryPage, "procesos": ProcessPage, "atajos": ShortcutsPage, "dotfiles": DotfilesPage}
