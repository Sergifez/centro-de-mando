"""Página «Apps»: gestor de AppImage. Todas viven en ~/Applications; desde aquí se ejecutan,
se actualizan (con la información de actualización que lleva cada AppImage) y se eliminan."""
import fnmatch
import json
import os
import re
import shutil
import struct
import subprocess
import tempfile
import urllib.request
from urllib.parse import urljoin

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QComboBox, QDialog, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit,
                             QListWidget, QListWidgetItem, QMessageBox, QPushButton, QScrollArea, QVBoxLayout,
                             QWidget)

APPS_DIR = os.path.expanduser("~/Applications")
DESKTOP_DIR = os.path.expanduser("~/.local/share/applications")
UA = {"User-Agent": "centro-de-mando/1.0"}


# ----------------------------------------------------------------- utilidades
def is_appimage(name):
    return name.lower().endswith(".appimage")


def list_apps():
    try:
        names = sorted(n for n in os.listdir(APPS_DIR) if is_appimage(n) and os.path.isfile(os.path.join(APPS_DIR, n)))
    except OSError:
        return []
    return [os.path.join(APPS_DIR, n) for n in names]


def pretty_name(path):
    n = re.sub(r"\.appimage$", "", os.path.basename(path), flags=re.I)
    n = re.sub(r"[-_.]?v?\d+(\.\d+)+.*$", "", n)  # versión y lo que venga detrás
    n = re.sub(r"[-_](linux|x86_64|x86-64|amd64|x64)\b", "", n, flags=re.I)
    return n.replace("_", " ").replace("-", " ").strip() or os.path.basename(path)


def version_of(path):
    m = re.search(r"[-_]v?(\d+(?:\.\d+)+)", os.path.basename(path))
    return m.group(1) if m else ""


def human(n):
    return f"{n / 1e9:.1f} GB" if n >= 1e9 else f"{n / 1e6:.0f} MB"


def desktop_entries():
    """{ruta del .desktop: texto} de los lanzadores del usuario."""
    out = {}
    try:
        for n in os.listdir(DESKTOP_DIR):
            if n.endswith(".desktop"):
                p = os.path.join(DESKTOP_DIR, n)
                try:
                    out[p] = open(p, encoding="utf-8", errors="replace").read()
                except OSError:
                    pass
    except OSError:
        pass
    return out


def desktop_for(path, entries=None):
    """Lanzadores cuyo Exec apunta a este AppImage."""
    return [p for p, t in (entries or desktop_entries()).items()
            if re.search(r"^(Try)?Exec=\"?" + re.escape(path) + r"(\"|\s|$)", t, re.M)]


def desktop_field(text, key):
    m = re.search(rf"^{key}=(.*)$", text, re.M)
    return m.group(1).strip() if m else ""


def rewrite_desktops(old, new):
    for p, t in desktop_entries().items():
        if old in t:
            with open(p, "w", encoding="utf-8") as f:
                f.write(t.replace(old, new))


def trash(path):
    """Papelera (recuperable); si no hay gio, borrado directo."""
    if shutil.which("gio") and subprocess.run(["gio", "trash", path], capture_output=True).returncode == 0:
        return
    os.unlink(path)


def update_info(path):
    """Cadena de actualización embebida en la sección ELF .upd_info, o ''."""
    try:
        with open(path, "rb") as f:
            h = f.read(64)
            if h[:4] != b"\x7fELF" or h[4] != 2:
                return ""
            shoff, = struct.unpack_from("<Q", h, 0x28)
            shentsize, shnum, shstrndx = struct.unpack_from("<HHH", h, 0x3A)
            f.seek(shoff)
            sh = f.read(shentsize * shnum)

            def sec(i):
                name, _t, _fl, _a, off, size = struct.unpack_from("<IIQQQQ", sh, i * shentsize)
                return name, off, size

            _n, stroff, strsize = sec(shstrndx)
            f.seek(stroff)
            strtab = f.read(strsize)
            for i in range(shnum):
                name, off, size = sec(i)
                if strtab[name:strtab.index(b"\0", name)] == b".upd_info":
                    f.seek(off)
                    return f.read(size).split(b"\0")[0].decode(errors="replace").strip()
    except (OSError, struct.error, ValueError):
        pass
    return ""


def _get(url, timeout=20):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout)


def check_update(path):
    """→ dict(state='sin-info'|'al-dia'|'nueva'|'error', ...). Con 'nueva': url, name, size, label."""
    info = update_info(path)
    local_size = os.path.getsize(path)
    base = os.path.basename(path)
    if not info:
        return {"state": "sin-info"}
    parts = info.split("|")
    try:
        if parts[0] == "gh-releases-zsync" and len(parts) >= 5:
            owner, repo, tag, pattern = parts[1:5]
            api = f"https://api.github.com/repos/{owner}/{repo}/releases/" + \
                  ("latest" if tag == "latest" else f"tags/{tag}")
            rel = json.load(_get(api))
            want = pattern[:-6] if pattern.endswith(".zsync") else pattern
            for a in rel.get("assets", []):
                if fnmatch.fnmatch(a["name"], want):
                    versioned = "*" in want
                    new = a["name"] != base if versioned else a["size"] != local_size
                    if not new:
                        return {"state": "al-dia"}
                    return {"state": "nueva", "url": a["browser_download_url"], "name": a["name"],
                            "size": a["size"], "label": rel.get("tag_name", a["name"])}
            return {"state": "error", "msg": "La última versión no tiene un archivo compatible"}
        if parts[0] == "zsync" and len(parts) >= 2:
            zurl = parts[1]
            head = _get(zurl).read(4096).split(b"\n\n")[0].decode(errors="replace")
            hdr = dict(l.split(": ", 1) for l in head.splitlines() if ": " in l)
            length = int(hdr.get("Length", 0))
            url = urljoin(zurl, hdr["URL"]) if "URL" in hdr else zurl[:-6]
            if length and length != local_size:
                return {"state": "nueva", "url": url, "name": hdr.get("Filename", base), "size": length,
                        "label": hdr.get("Filename", "nueva versión")}
            return {"state": "al-dia"}
    except Exception as e:  # red caída, límite de la API, etc.
        return {"state": "error", "msg": str(e)[:120]}
    return {"state": "sin-info"}


# ------------------------------------------------------------------- hilos
class Worker(QThread):
    progress = pyqtSignal(int)
    done = pyqtSignal(object)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        try:
            self.done.emit(self.fn(self.progress.emit))
        except Exception as e:
            self.done.emit({"state": "error", "msg": str(e)[:160]})


def download_update(path, upd, emit):
    """Descarga la nueva versión junto a la actual y, solo si es válida, sustituye a la vieja."""
    new_path = os.path.join(os.path.dirname(path), os.path.basename(upd["name"]))
    part = os.path.join(os.path.dirname(path), "." + os.path.basename(new_path) + ".part")
    try:
        with _get(upd["url"], timeout=30) as r, open(part, "wb") as f:
            total = int(r.headers.get("Content-Length") or upd.get("size") or 0)
            got, last = 0, -1
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
                got += len(chunk)
                pct = got * 100 // total if total else 0
                if pct != last:
                    last = pct
                    emit(pct)
        with open(part, "rb") as f:
            if f.read(4) != b"\x7fELF":
                raise RuntimeError("Lo descargado no es un AppImage válido")
        os.chmod(part, 0o755)
        if new_path != path:
            os.replace(part, new_path)
            rewrite_desktops(path, new_path)
            trash(path)  # la versión anterior queda en la papelera
        else:
            os.replace(part, new_path)
    finally:
        if os.path.exists(part):
            os.unlink(part)
    return {"state": "hecho", "path": new_path}


def scattered():
    """AppImage fuera de ~/Applications (home, hasta 3 niveles, sin carpetas ocultas)."""
    home, found = os.path.expanduser("~"), []
    for root, dirs, files in os.walk(home):
        depth = root[len(home):].count(os.sep)
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", "snap")
                   and os.path.join(root, d) != APPS_DIR and depth < 3
                   and not os.path.ismount(os.path.join(root, d))]  # p. ej. ~/Drive (rclone): no tocar
        for fn in files:
            p = os.path.join(root, fn)
            if is_appimage(fn) and os.path.isfile(p) and not os.path.islink(p):
                found.append(p)
    return sorted(found)



# ------------------------------------------------------------ entrada de menú
# (categoría freedesktop, nombre en el menú de Openbox, nombre en español) — las que entiende obamenu
SECTIONS = [("Office", "Office", "Oficina"), ("Development", "Development", "Desarrollo"),
            ("Graphics", "Graphics", "Gráficos"), ("Network", "Internet", "Internet"), ("Game", "Games", "Juegos"),
            ("System", "System", "Sistema"), ("AudioVideo", "Multimedia", "Multimedia"),
            ("Utility", "Utilities", "Utilidades"), ("Settings", "Settings", "Ajustes"), ("Science", "Science", "Ciencia")]
ALIASES = {"Audio": "AudioVideo", "Video": "AudioVideo", "Electronics": "Science", "Education": "Science",
           "Math": "Science", "TextEditor": "Utility", "Viewer": "Office", "Player": "AudioVideo"}
ICON_DIR = os.path.expanduser("~/.local/share/icons/hicolor")


def guess_section(cats):
    known = {c for c, _m, _e in SECTIONS}
    for c in cats:
        c = ALIASES.get(c, c)
        if c in known:
            return c
    return "Utility"


def slug(path):
    return re.sub(r"[^a-z0-9]+", "-", pretty_name(path).lower()).strip("-") or "app"


def read_meta(path):
    """Extrae del AppImage su .desktop y su icono (sin ejecutarlo). → dict(name, cats, icon_file)."""
    meta = {"name": pretty_name(path), "cats": [], "icon_file": ""}
    with tempfile.TemporaryDirectory(prefix="appimg-") as tmp:
        def extract(pattern):
            try:
                subprocess.run([path, "--appimage-extract", pattern], cwd=tmp, capture_output=True, timeout=90)
            except (OSError, subprocess.SubprocessError):
                pass
        extract("*.desktop")
        root = os.path.join(tmp, "squashfs-root")
        found = sorted(f for f in os.listdir(root) if f.endswith(".desktop")) if os.path.isdir(root) else []
        icon = ""
        if found:
            text = open(os.path.join(root, found[0]), encoding="utf-8", errors="replace").read()
            meta["name"] = desktop_field(text, "Name") or meta["name"]
            meta["cats"] = [c for c in desktop_field(text, "Categories").split(";") if c]
            icon = desktop_field(text, "Icon")
        for cand in ([icon + ".png", icon + ".svg"] if icon else []) + [".DirIcon"]:
            extract(cand)
            f = os.path.realpath(os.path.join(root, cand)) if os.path.isdir(root) else ""
            if f.startswith(os.path.realpath(root) + os.sep) and os.path.isfile(f):
                ext = ".svg" if f.lower().endswith(".svg") else ".png"
                dest = os.path.join(tempfile.gettempdir(), f"appimg-icon-{slug(path)}{ext}")
                shutil.copy2(f, dest)
                meta["icon_file"] = dest
                break
    return meta


def install_icon(src, name):
    if not src or not os.path.isfile(src):
        return ""
    ext = os.path.splitext(src)[1]
    d = os.path.join(ICON_DIR, "scalable" if ext == ".svg" else "256x256", "apps")
    os.makedirs(d, exist_ok=True)
    shutil.copy2(src, os.path.join(d, name + ext))
    return name


def write_launcher(path, name, section, icon_file="", desktop=None):
    """Crea (o actualiza) el .desktop del AppImage con una sola categoría: así aparece en una única sección."""
    os.makedirs(DESKTOP_DIR, exist_ok=True)
    if desktop:  # existente: solo cambia nombre y sección
        text = open(desktop, encoding="utf-8").read()
        text = re.sub(r"^Name=.*$", lambda _m: f"Name={name}", text, count=1, flags=re.M)
        if re.search(r"^Categories=", text, re.M):
            text = re.sub(r"^Categories=.*$", lambda _m: f"Categories={section};", text, count=1, flags=re.M)
        else:
            text = text.replace("[Desktop Entry]\n", f"[Desktop Entry]\nCategories={section};\n", 1)
        open(desktop, "w", encoding="utf-8").write(text)
        return desktop
    ident = "appimage-" + slug(path)
    icon = install_icon(icon_file, ident)
    desktop = os.path.join(DESKTOP_DIR, ident + ".desktop")
    with open(desktop, "w", encoding="utf-8") as f:
        f.write("[Desktop Entry]\nType=Application\n" f"Name={name}\nExec=\"{path}\"\n"
                f"Icon={icon}\nTerminal=false\nCategories={section};\nComment=AppImage ({os.path.basename(path)})\n")
    return desktop


class MenuDialog(QDialog):
    """Elegir nombre y sección del menú para un AppImage."""

    def __init__(self, parent, name, section, existing=False):
        super().__init__(parent)
        self.setWindowTitle("Sección del menú" if existing else "Añadir al menú")
        self.resize(420, 10)
        self.remove = False
        form = QFormLayout(self)
        self.name = QLineEdit(name)
        form.addRow("Nombre en el menú", self.name)
        self.combo = QComboBox()
        for cat, menu, es in SECTIONS:
            self.combo.addItem(f"{es}  ({menu})", cat)
        self.combo.setCurrentIndex(max(0, [c for c, _m, _e in SECTIONS].index(section)))
        form.addRow("Sección", self.combo)
        note = QLabel("Aparece en Menú ▸ Applications ▸ la sección elegida.")
        note.setObjectName("muted")
        form.addRow(note)
        row = QHBoxLayout()
        if existing:
            rm = QPushButton("Quitar del menú")
            rm.clicked.connect(self._remove)
            row.addWidget(rm)
        ok, no = QPushButton("Guardar"), QPushButton("Cancelar")
        ok.setObjectName("primary")
        ok.clicked.connect(self.accept)
        no.clicked.connect(self.reject)
        row.addStretch(1)
        row.addWidget(no)
        row.addWidget(ok)
        form.addRow(row)

    def _remove(self):
        self.remove = True
        self.accept()

    def section(self):
        return self.combo.currentData()


# ------------------------------------------------------------------- diálogo
class AdoptDialog(QDialog):
    def __init__(self, parent, paths):
        super().__init__(parent)
        self.setWindowTitle("Traer AppImage a ~/Applications")
        self.resize(640, 380)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Se mueven a ~/Applications (mismo disco: es instantáneo) y se corrigen los lanzadores "
                             "del menú que los usan. Desmarca los que quieras dejar donde están."))
        lay.itemAt(0).widget().setWordWrap(True)
        self.list = QListWidget()
        newest = {}
        for p in paths:  # entre varias versiones del mismo programa, solo la más reciente va marcada
            key = pretty_name(p).lower()
            if key not in newest or os.path.getmtime(p) > os.path.getmtime(newest[key]):
                newest[key] = p
        for p in paths:
            it = QListWidgetItem(f"{p.replace(os.path.expanduser('~'), '~')}   ({human(os.path.getsize(p))})")
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked if newest[pretty_name(p).lower()] == p else Qt.CheckState.Unchecked)
            it.setData(Qt.ItemDataRole.UserRole, p)
            self.list.addItem(it)
        lay.addWidget(self.list)
        row = QHBoxLayout()
        ok, no = QPushButton("Mover los marcados"), QPushButton("Cancelar")
        ok.setObjectName("primary")
        ok.clicked.connect(self.accept)
        no.clicked.connect(self.reject)
        row.addStretch(1)
        row.addWidget(no)
        row.addWidget(ok)
        lay.addLayout(row)

    def chosen(self):
        return [self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count())
                if self.list.item(i).checkState() == Qt.CheckState.Checked]


def adopt(paths):
    """Mueve los AppImage a APPS_DIR y reescribe los lanzadores. → (movidos, avisos)."""
    os.makedirs(APPS_DIR, exist_ok=True)
    moved, notes = [], []
    for p in paths:
        dest = os.path.join(APPS_DIR, os.path.basename(p))
        if os.path.exists(dest):
            notes.append(f"{os.path.basename(p)}: ya existe en ~/Applications, no se mueve")
            continue
        shutil.move(p, dest)
        rewrite_desktops(p, dest)
        moved.append(dest)
    return moved, notes


# -------------------------------------------------------------------- página
class AppsPage(QWidget):
    def __init__(self, win=None):
        super().__init__()
        self.win = win
        self.state = {}      # ruta → resultado de la última comprobación
        self.busy = {}       # ruta → texto mientras se comprueba/descarga
        self.threads = []
        self.labels = {}
        top = QVBoxLayout(self)
        top.setContentsMargins(24, 16, 24, 8)
        h = QLabel("Apps (AppImage)")
        h.setObjectName("h1")
        top.addWidget(h)
        self.sub = QLabel()
        self.sub.setObjectName("muted")
        self.sub.setWordWrap(True)
        top.addWidget(self.sub)
        bar = QHBoxLayout()
        for text, fn in (("Buscar actualizaciones", self.check_all), ("Añadir…", self.add),
                         ("Traer las dispersas…", self.bring), ("Abrir carpeta", self.open_dir)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            bar.addWidget(b)
        bar.addStretch(1)
        top.addLayout(bar)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.inner = QWidget()
        self.col = QVBoxLayout(self.inner)
        self.col.setContentsMargins(0, 4, 8, 4)
        self.col.setSpacing(8)
        scroll.setWidget(self.inner)
        top.addWidget(scroll, 1)

    def showEvent(self, e):
        self.refresh()

    def log(self, m):
        if self.win:
            self.win.log(m)

    # ---- listado
    def refresh(self):
        while self.col.count():
            w = self.col.takeAt(0).widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        self.labels = {}
        apps = list_apps()
        entries = desktop_entries()
        total = sum(os.path.getsize(p) for p in apps)
        self.sub.setText(f"{len(apps)} aplicaciones en ~/Applications · {human(total)}. "
                         "Cada una se actualiza con la información que lleva incorporada; si no la tiene, "
                         "hay que bajar la nueva versión a mano (botón Añadir).")
        for p in apps:
            self.col.addWidget(self._card(p, entries))
        if not apps:
            self.col.addWidget(QLabel("No hay AppImage en ~/Applications. Usa «Traer las dispersas…» o «Añadir…»."))
        self.col.addStretch(1)

    def _card(self, path, entries):
        d = next(iter(desktop_for(path, entries)), None)
        text = entries.get(d, "")
        name = desktop_field(text, "Name") or pretty_name(path)
        card = QFrame()
        card.setObjectName("card")
        card.setProperty("plain", True)
        card.setMinimumHeight(64)
        lay = QHBoxLayout(card)
        lay.setContentsMargins(14, 10, 14, 10)
        ic = QLabel()
        icon = QIcon.fromTheme(desktop_field(text, "Icon")) if text else QIcon()
        if not icon.isNull():
            ic.setPixmap(icon.pixmap(36, 36))
        else:
            ic.setText("▣")
            ic.setStyleSheet("font-size:28px;color:#3aa8e0;")
        ic.setFixedWidth(40)
        lay.addWidget(ic)
        col = QVBoxLayout()
        col.setSpacing(2)
        v = version_of(path)
        t = QLabel(name + (f"  ·  {v}" if v else ""))
        t.setObjectName("rowtitle")
        sub = QLabel(f"{os.path.basename(path)}  ·  {human(os.path.getsize(path))}"
                     + (f"  ·  menú: {self._section_label(text)}" if d else "  ·  sin entrada de menú"))
        sub.setObjectName("muted")
        col.addWidget(t)
        col.addWidget(sub)
        lay.addLayout(col, 1)
        st = self._status(path)
        stl = QLabel(st[0])
        stl.setStyleSheet(f"color:{st[1]};")
        self.labels[path] = stl
        lay.addWidget(stl)
        run = QPushButton("Ejecutar")
        run.setObjectName("primary")
        run.clicked.connect(lambda _c=False, p=path: self.launch(p))
        upd = QPushButton("Actualizar" if self.state.get(path, {}).get("state") == "nueva" else "Comprobar")
        upd.setEnabled(path not in self.busy)
        upd.clicked.connect(lambda _c=False, p=path: self.update_one(p))
        mn = QPushButton("Menú…" if d else "Añadir al menú…")
        mn.setEnabled(path not in self.busy)
        mn.clicked.connect(lambda _c=False, p=path: self.menu_entry(p))
        rm = QPushButton("Eliminar")
        rm.setEnabled(path not in self.busy)
        rm.clicked.connect(lambda _c=False, p=path: self.remove(p))
        for b in (run, upd, mn, rm):
            lay.addWidget(b)
        return card

    def _status(self, path):
        if path in self.busy:
            return self.busy[path], "#e0b43a"
        s = self.state.get(path)
        if not s:
            return "", "#7f8b99"
        return {
            "al-dia": ("✓ Al día", "#5fb878"),
            "nueva": (f"⬆ {s.get('label', 'Nueva versión')} · {human(s.get('size', 0))}", "#e0b43a"),
            "sin-info": ("Sin información de actualización", "#7f8b99"),
            "error": (f"✗ {s.get('msg', 'Error')}", "#e0594f"),
            "hecho": ("✓ Actualizada", "#5fb878"),
        }.get(s["state"], ("", "#7f8b99"))

    # ---- acciones
    def launch(self, path):
        try:
            subprocess.Popen([path], cwd=os.path.expanduser("~"), start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.log(f"▶ Lanzada {pretty_name(path)}")
        except OSError as e:
            QMessageBox.warning(self, "No se pudo ejecutar", str(e))

    def _start(self, path, fn, label, after):
        self.busy[path] = label
        w = Worker(fn)
        self.threads.append(w)
        w.progress.connect(lambda pct, p=path, l=label: self._progress(p, l, pct))

        def done(res, p=path):
            self.threads.remove(w)
            self.busy.pop(p, None)
            after(p, res)
            self.refresh()

        w.done.connect(done)
        w.start()
        self.refresh()

    def _progress(self, path, label, pct):
        if path in self.busy:
            self.busy[path] = f"{label} {pct} %"
            lab = self.labels.get(path)
            if lab:
                lab.setText(self.busy[path])

    def check_all(self):
        for p in list_apps():
            if p not in self.busy:
                self._start(p, lambda _emit, p=p: check_update(p), "Comprobando…", self._checked)

    def update_one(self, path):
        s = self.state.get(path)
        if s and s["state"] == "nueva":
            if QMessageBox.question(self, "Actualizar", f"¿Descargar {s['label']} ({human(s['size'])})?\n"
                                    "La versión actual irá a la papelera cuando termine bien.") != \
                    QMessageBox.StandardButton.Yes:
                return
            self.log(f"▶ Actualizando {pretty_name(path)} a {s['label']}")
            self._start(path, lambda emit: download_update(path, s, emit), "Descargando", self._updated)
        else:
            self._start(path, lambda _emit: check_update(path), "Comprobando…", self._checked)

    def _checked(self, path, res):
        self.state[path] = res

    def _updated(self, path, res):
        if res["state"] == "hecho":
            self.state.pop(path, None)
            self.state[res["path"]] = {"state": "hecho"}
            self.log(f"✓ {pretty_name(res['path'])} actualizada")
        else:
            self.state[path] = res
            self.log(f"✗ Falló la actualización de {pretty_name(path)}: {res.get('msg', '')}")

    def remove(self, path):
        launchers = desktop_for(path)
        extra = "\nTambién se quitará su entrada del menú." if launchers else ""
        if QMessageBox.question(self, "Eliminar", f"¿Eliminar {os.path.basename(path)} "
                                f"({human(os.path.getsize(path))})?{extra}\n\nVa a la papelera, se puede recuperar.") != \
                QMessageBox.StandardButton.Yes:
            return
        try:
            trash(path)
            for d in launchers:
                trash(d)
            self.log(f"✓ {os.path.basename(path)} movida a la papelera")
        except OSError as e:
            QMessageBox.warning(self, "No se pudo eliminar", str(e))
        self.state.pop(path, None)
        self.refresh()

    @staticmethod
    def _section_label(text):
        cats = [c for c in desktop_field(text, "Categories").split(";") if c]
        sec = guess_section(cats) if cats else ""
        return next((es for c, _m, es in SECTIONS if c == sec), "sin sección")

    def menu_entry(self, path):
        existing = next(iter(desktop_for(path)), None)
        if existing:
            text = open(existing, encoding="utf-8", errors="replace").read()
            cats = [c for c in desktop_field(text, "Categories").split(";") if c]
            self._menu_dialog(path, desktop_field(text, "Name") or pretty_name(path), guess_section(cats),
                              existing, "")
        else:  # primera vez: leer nombre, categorías e icono del propio AppImage
            self._start(path, lambda _emit: read_meta(path), "Leyendo el AppImage…", self._meta_ready)

    def _meta_ready(self, path, meta):
        if meta.get("state") == "error":
            meta = {"name": pretty_name(path), "cats": [], "icon_file": ""}
        self._menu_dialog(path, meta["name"], guess_section(meta["cats"]), None, meta["icon_file"])

    def _menu_dialog(self, path, name, section, existing, icon_file):
        d = MenuDialog(self, name, section, existing=bool(existing))
        if not d.exec():
            return
        try:
            if d.remove:
                trash(existing)
                self.log(f"✓ {pretty_name(path)} quitada del menú")
            else:
                write_launcher(path, d.name.text().strip() or name, d.section(), icon_file, existing)
                sec = next(m for c, m, _e in SECTIONS if c == d.section())
                self.log(f"✓ {d.name.text().strip() or name} en el menú, sección {sec}")
        except OSError as e:
            QMessageBox.warning(self, "No se pudo guardar", str(e))
        if icon_file and os.path.exists(icon_file):
            os.unlink(icon_file)  # copia temporal de read_meta
        self.refresh()

    def add(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Elegir AppImage", os.path.expanduser("~"),
                                                "AppImage (*.AppImage *.appimage)")
        if files:
            self._adopt(files)

    def bring(self):
        found = scattered()
        if not found:
            QMessageBox.information(self, "Traer las dispersas", "No hay AppImage fuera de ~/Applications.")
            return
        d = AdoptDialog(self, found)
        if d.exec() and d.chosen():
            self._adopt(d.chosen())

    def _adopt(self, paths):
        try:
            moved, notes = adopt(paths)
        except OSError as e:
            QMessageBox.warning(self, "No se pudo mover", str(e))
            return
        for m in moved:
            os.chmod(m, os.stat(m).st_mode | 0o111)
        self.log(f"✓ {len(moved)} AppImage movidos a ~/Applications")
        if notes:
            QMessageBox.information(self, "Avisos", "\n".join(notes))
        self.refresh()

    def open_dir(self):
        os.makedirs(APPS_DIR, exist_ok=True)
        subprocess.Popen(["xdg-open", APPS_DIR], start_new_session=True)
