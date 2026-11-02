"""Página «Archivos»: abre en el editor de texto los archivos de configuración de tint2, conky, picom,
Openbox y otros, y recarga la herramienta cuando se ha editado."""
import glob
import os
import re
import shutil
import subprocess

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QScrollArea,
                             QVBoxLayout, QWidget)

import deskcfg as dc
import notify

HOME = os.path.expanduser("~")
CONF = os.path.join(HOME, ".config")

# (orden de preferencia) comando, nombre. Los de terminal se lanzan con x-terminal-emulator.
EDITORS = [("subl", "Sublime Text"), ("mousepad", "Mousepad"), ("gedit", "gedit"), ("xed", "Xed"),
           ("pluma", "Pluma"), ("geany", "Geany"), ("kate", "Kate"), ("code", "Visual Studio Code"),
           ("nano", "nano (terminal)"), ("vim", "vim (terminal)")]
TERMINAL_EDITORS = {"nano", "vim"}


def available_editors():
    return [(c, n) for c, n in EDITORS if shutil.which(c)]


def chosen_editor():
    """Comando del editor: el elegido en el panel si sigue instalado, si no el primero disponible."""
    want = notify.load_prefs().get("editor", "")
    av = [c for c, _n in available_editors()]
    if want in av:
        return want
    return av[0] if av else ""


def editor_argv(path):
    ed = chosen_editor()
    if not ed:
        return None
    if ed in TERMINAL_EDITORS:
        return ["x-terminal-emulator", "-e", ed, path]
    return [ed, path]


def open_in_editor(path):
    argv = editor_argv(path)
    if not argv:
        raise RuntimeError("No hay ningún editor de texto instalado (prueba con: sudo apt install mousepad).")
    subprocess.Popen(argv, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _existing(paths):
    return [p for p in paths if os.path.isfile(p)]


def groups():
    """[(id, título, descripción, [archivos], acción de recarga | None)] con lo que exista en este equipo."""
    tint = sorted(f for f in glob.glob(os.path.join(dc.TINT_DIR, "*"))
                  if os.path.isfile(f) and ".backup" not in f and re.search(r"tint2rc_?$", f))
    conky = []
    for pat in ("*/*.conkyrc", "*.conkyrc", ".conkyrc", "conky.vars.lua", "*/*.lua"):
        conky += glob.glob(os.path.join(CONF, "conky", pat))
    conky = sorted({f for f in conky if os.path.isfile(f)})
    ob = _existing([os.path.join(CONF, "openbox", n) for n in ("rc.xml", "menu.xml", "autostart", "environment")])
    other = _existing([os.path.join(CONF, "rofi", "config.rasi"), os.path.join(CONF, "gtk-3.0", "settings.ini"),
                       os.path.join(CONF, "terminator", "config"), os.path.join(HOME, ".bashrc")])
    out = [
        ("tint2", "Barras tint2", "Barra de tareas y barra del menú. Los archivos acabados en _ están desactivados.",
         tint, "tint2"),
        ("conky", "Conky", "Monitores y chuleta de atajos del escritorio.", conky, "conky"),
        ("picom", "Compositor (picom)", "Sombras, fundidos y opacidades.", _existing([dc.PICOM_CONF]), "picom"),
        ("openbox", "Openbox", "Ventanas, atajos, menú y programas de arranque.", ob, "openbox"),
        ("otros", "Otros", "Rofi, tema GTK, terminal y shell.", other, None),
    ]
    return [g for g in out if g[3]]


def reload_group(action):
    """Recarga la herramienta para que tome los cambios del archivo editado."""
    if action == "conky":
        for rc in [f for f in glob.glob(os.path.join(CONF, "conky", "*", "*.conkyrc")) + [os.path.join(CONF, "conky", ".conkyrc")]
                   if os.path.isfile(f) and dc.conky_pids(f)]:
            dc.later(("conky", rc))
    elif action:
        dc.later(action)
    dc.flush()


def short(path):
    p = path.replace(HOME, "~")
    real = os.path.realpath(path)
    return p + ("   →  dotfiles" if os.path.islink(path) and "/dotfiles/" in real else "")


class ConfigPage(QWidget):
    def __init__(self, win=None):
        super().__init__()
        self.win = win
        top = QVBoxLayout(self)
        top.setContentsMargins(24, 16, 24, 8)
        h = QLabel("Archivos de configuración")
        h.setObjectName("h1")
        top.addWidget(h)
        sub = QLabel("Abre en tu editor de texto los archivos de cada herramienta. Después de guardar, pulsa "
                     "«Recargar» en su grupo para que los cambios se vean. Al editar aquí no se hace copia de "
                     "seguridad: si el archivo está en ~/dotfiles, git guarda el historial.")
        sub.setObjectName("muted")
        sub.setWordWrap(True)
        top.addWidget(sub)
        row = QHBoxLayout()
        row.addWidget(QLabel("Editor de texto"))
        self.combo = QComboBox()
        self.combo.addItem("Automático", "")
        for c, n in available_editors():
            self.combo.addItem(n, c)
        cur = notify.load_prefs().get("editor", "")
        i = self.combo.findData(cur)
        self.combo.setCurrentIndex(max(0, i))
        self.combo.currentIndexChanged.connect(self.save_editor)
        row.addWidget(self.combo)
        self.which = QLabel()
        self.which.setObjectName("muted")
        row.addWidget(self.which)
        row.addStretch(1)
        top.addLayout(row)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        self.col = QVBoxLayout(inner)
        self.col.setContentsMargins(0, 6, 8, 6)
        self.col.setSpacing(8)
        scroll.setWidget(inner)
        top.addWidget(scroll, 1)
        self.update_which()

    def showEvent(self, e):
        self.refresh()

    def update_which(self):
        ed = dict(EDITORS).get(chosen_editor(), "")
        self.which.setText(f"Se usará: {ed}" if ed else "No hay editor instalado")

    def save_editor(self):
        p = notify.load_prefs()
        p["editor"] = self.combo.currentData()
        notify.save_prefs(p)
        self.update_which()

    def refresh(self):
        while self.col.count():
            w = self.col.takeAt(0).widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        for _gid, title, desc, files, action in groups():
            self.col.addWidget(self._group(title, desc, files, action))
        self.col.addStretch(1)

    def _group(self, title, desc, files, action):
        card = QFrame()
        card.setObjectName("card")
        card.setProperty("plain", True)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 12, 16, 12)
        head = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(2)
        t = QLabel(title)
        t.setObjectName("rowtitle")
        d = QLabel(desc)
        d.setObjectName("muted")
        d.setWordWrap(True)
        col.addWidget(t)
        col.addWidget(d)
        head.addLayout(col, 1)
        if action:
            b = QPushButton("Recargar")
            b.setToolTip("Reinicia la herramienta para que lea los archivos guardados")
            b.clicked.connect(lambda _c=False, a=action, n=title: self.reload(a, n))
            head.addWidget(b)
        lay.addLayout(head)
        for f in files:
            line = QHBoxLayout()
            name = os.path.basename(f)
            inactive = name.endswith("_")
            lab = QLabel(f"{name}" + ("  (desactivado)" if inactive else ""))
            lab.setStyleSheet("font-weight:bold;" + ("color:#7f8b99;" if inactive else ""))
            line.addWidget(lab)
            path = QLabel(short(f))
            path.setObjectName("muted")
            line.addWidget(path, 1)
            e = QPushButton("Editar")
            e.clicked.connect(lambda _c=False, p=f: self.edit(p))
            line.addWidget(e)
            lay.addLayout(line)
        return card

    def edit(self, path):
        try:
            open_in_editor(path)
            if self.win:
                self.win.log(f"▶ Abierto en el editor: {path.replace(HOME, '~')}")
        except (RuntimeError, OSError) as e:
            QMessageBox.warning(self, "No se pudo abrir", str(e))

    def reload(self, action, name):
        try:
            reload_group(action)
            if self.win:
                self.win.log(f"✓ {name} recargado")
        except Exception as e:
            QMessageBox.warning(self, "No se pudo recargar", str(e))
