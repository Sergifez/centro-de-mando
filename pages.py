"""Páginas de información (no son ajustes): Batería, Procesos y Atajos."""
import glob
import os
import re
import signal
import subprocess
import time
import xml.etree.ElementTree as ET

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (QFrame, QProgressBar, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
                             QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

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
        out.append((pretty_key(kb.get("key", "")), " → ".join(acts)))
    return out


class ShortcutsPage(QWidget):
    def __init__(self, win=None):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 16, 24, 8)
        self.sub = _header(outer, "Atajos de teclado", "Los de Openbox (rc.xml). Solo lectura; la chuleta de conky es un reflejo de esta lista.")
        self.filter = QLineEdit()
        self.filter.setObjectName("search")
        self.filter.setPlaceholderText("Filtrar atajos o acciones…")
        self.filter.textChanged.connect(self.fill)
        outer.addWidget(self.filter)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Atajo", "Acción"])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        outer.addWidget(self.table, 1)
        self.binds = []

    def refresh(self):
        self.binds = parse_keybinds()
        self.fill()

    def fill(self):
        q = self.filter.text().lower().strip()
        rows = [b for b in self.binds if q in (b[0] + " " + b[1]).lower()]
        self.table.setRowCount(len(rows))
        for i, (k, a) in enumerate(rows):
            self.table.setItem(i, 0, QTableWidgetItem(k))
            self.table.setItem(i, 1, QTableWidgetItem(a))
        self.sub.setText(f"{len(rows)} de {len(self.binds)} atajos · solo lectura; edita rc.xml o usa obconf.")


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
        outer = QVBoxLayout(self)
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
        outer.addStretch(1)
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
        self.cache.setText(_mb(_dir_size(os.path.expanduser("~/.cache"))) if not self.busy else "…")


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


PAGES = {"actualizaciones": UpdatesPage, "disco": DiskPage, "bateria": BatteryPage, "procesos": ProcessPage, "atajos": ShortcutsPage}
