"""Edición segura de la configuración de escritorio: autostart, conky, tint2, picom y Openbox.

Todo cambio en un archivo hace antes una copia en ~/.config/panel-portatil/backups/.
Las recargas (reiniciar tint2, picom, conky, openbox) se acumulan con `later()` y se
ejecutan una sola vez al terminar el lote (`end()`), así varios cambios = un reinicio.
"""
import glob
import os
import re
import shutil
import signal
import subprocess
import time

HOME = os.path.expanduser("~")
CONF = os.path.join(HOME, ".config")
BACKUP_DIR = os.path.join(CONF, "panel-portatil", "backups")
AUTOSTART = os.path.join(CONF, "openbox", "autostart")
RC_XML = os.path.join(CONF, "openbox", "rc.xml")
PICOM_CONF = os.path.join(CONF, "picom.conf")
TINT_DIR = os.path.join(CONF, "tint2")
TINT_SESSION = os.path.join(HOME, ".local", "bin", "tint2-session")
MARK = "#PANEL# "  # prefijo con el que desactivamos una línea del autostart

_backed = set()
_post = set()
_batch = 0


# ------------------------------------------------------------------- archivos
def read(path, default=""):
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return default


def write(path, text):
    old = read(path, None)
    if old == text:
        return
    if old is not None and path not in _backed:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        shutil.copy2(os.path.realpath(path), os.path.join(BACKUP_DIR, f"{os.path.basename(path)}.{stamp}"))
        _backed.add(path)
    with open(path, "w") as f:  # abre a través del enlace simbólico (dotfiles)
        f.write(text)


def sub_group(path, pattern, value, flags=re.M):
    """Reemplaza el grupo 2 de `pattern` (3 grupos: antes, valor, después)."""
    txt = read(path)
    new, n = re.subn(pattern, lambda m: m.group(1) + str(value) + m.group(3), txt, count=1, flags=flags)
    if not n:
        raise RuntimeError(f"No encuentro el ajuste en {os.path.basename(path)}")
    write(path, new)


def find_group(path, pattern, default="", flags=re.M):
    m = re.search(pattern, read(path), flags)
    return m.group(2) if m else default


# ------------------------------------------------------------------ recargas
def begin():
    global _batch
    _batch += 1


def end():
    global _batch
    _batch = max(0, _batch - 1)
    if _batch == 0:
        flush()


def later(action):
    _post.add(action)


def flush():
    todo = sorted(_post, key=str)
    _post.clear()
    errors = []
    for a in todo:
        try:
            if a == "tint2":
                subprocess.Popen([TINT_SESSION, "restart"], start_new_session=True,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif a == "picom":
                picom_restart()
            elif a == "openbox":
                subprocess.run(["openbox", "--reconfigure"], check=True, timeout=10)
            elif isinstance(a, tuple) and a[0] == "conky":
                if conky_pids(a[1]):
                    conky_stop(a[1])
                    conky_start(a[1])
        except Exception as e:
            errors.append(f"{a}: {e}")
    if errors:
        raise RuntimeError("\n".join(errors))


# ---------------------------------------------------------------------- conky
def conky_pids(rc):
    pids = []
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        try:
            argv = open(f"/proc/{d}/cmdline", "rb").read().split(b"\0")
        except OSError:
            continue
        if argv and os.path.basename(argv[0].decode(errors="ignore")) == "conky" and rc.encode() in argv:
            pids.append(int(d))
    return pids


def conky_start(rc):
    subprocess.Popen(["conky", "-q", "-d", "-c", rc], start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def conky_stop(rc):
    for pid in conky_pids(rc):
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    time.sleep(0.3)


def lua_get(path, key, default=""):
    m = re.search(rf"^[ \t]*{key}[ \t]*=[ \t]*(.+?),?[ \t]*$", read(path), re.M)
    return m.group(1).strip("'\"") if m else default


def lua_set(path, key, value, quote=False):
    v = f"'{value}'" if quote else str(value)
    sub_group(path, rf"^([ \t]*{key}[ \t]*=[ \t]*)(.+?)(,?[ \t]*)$", v)


# ----------------------------------------------------------------------- tint2
def ini_get(path, key, default=""):
    return find_group(path, rf"^({re.escape(key)}[ \t]*=[ \t]*)(.*?)([ \t]*)$", default)


def ini_set(path, key, value):
    try:
        sub_group(path, rf"^({re.escape(key)}[ \t]*=[ \t]*)(.*?)([ \t]*)$", value)
    except RuntimeError:
        write(path, read(path).rstrip("\n") + f"\n{key} = {value}\n")


def tint_variants():
    """Archivos taskbar*.tint2rc[_]: devuelve {nombre: activo?}."""
    res = {}
    for f in glob.glob(os.path.join(TINT_DIR, "taskbar*")):
        m = re.match(r"^(taskbar(?:_\w+)?)\.tint2rc(_?)$", os.path.basename(f))
        if m:
            res[m.group(1)] = (m.group(2) == "")
    return res


def tint_active_taskbar():
    for name, on in tint_variants().items():
        if on:
            return os.path.join(TINT_DIR, name + ".tint2rc")
    return None


def tint_set_taskbar(chosen):
    for name, on in tint_variants().items():
        src = os.path.join(TINT_DIR, name + (".tint2rc" if on else ".tint2rc_"))
        dst = os.path.join(TINT_DIR, name + (".tint2rc" if name == chosen else ".tint2rc_"))
        if src != dst:
            os.rename(src, dst)
    later("tint2")


def tint_menu_on():
    return os.path.exists(os.path.join(TINT_DIR, "menu.tint2rc"))


def tint_set_menu(on):
    on_p, off_p = (os.path.join(TINT_DIR, "menu.tint2rc" + s) for s in ("", "_"))
    src, dst = (off_p, on_p) if on else (on_p, off_p)
    if os.path.exists(src):
        os.rename(src, dst)
    later("tint2")


# ----------------------------------------------------------------------- picom
def picom_get(key, default=""):
    m = re.search(rf"^{re.escape(key)}[ \t]*=[ \t]*(.*?);", read(PICOM_CONF), re.M)
    return m.group(1) if m else default


def picom_set(key, value):
    txt = read(PICOM_CONF)
    pat = re.compile(rf"^{re.escape(key)}[ \t]*=.*$", re.M)
    line = f"{key} = {value};"
    write(PICOM_CONF, pat.sub(lambda m: line, txt, 1) if pat.search(txt) else txt.rstrip("\n") + f"\n{line}\n")
    later("picom")


def picom_running():
    return subprocess.run(["pgrep", "-x", "picom"], capture_output=True).returncode == 0


def picom_restart():
    if not picom_running():
        return
    subprocess.run(["pkill", "-x", "picom"])
    time.sleep(0.4)
    subprocess.Popen(["picom", "--backend", "xrender"], start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def conky_opacity_get():
    m = re.search(r"(\d+):class_g\s*=\s*'ConkyAtajos'", read(PICOM_CONF))
    return int(m.group(1)) if m else 100


def conky_opacity_set(pct):
    txt = read(PICOM_CONF)
    rule = f"{int(pct)}:class_g = 'ConkyAtajos'"
    if re.search(r"\d+:class_g\s*=\s*'ConkyAtajos'", txt):
        txt = re.sub(r"\d+:class_g\s*=\s*'ConkyAtajos'", rule, txt, count=1)
    else:
        txt = txt.rstrip("\n") + f'\nopacity-rule = [ "{rule}" ];\n'
    write(PICOM_CONF, txt)
    later("picom")


# --------------------------------------------------------------------- openbox
RC_PATTERNS = {
    "theme": r"(<theme>\s*<name>)(.*?)(</name>)",
    "layout": r"(<titleLayout>)(.*?)(</titleLayout>)",
    "desktops": r"(<desktops>.*?<number>)(\d+)(</number>)",
    "follow": r"(<followMouse>)(yes|no)(</followMouse>)",
}


def rc_get(key, default=""):
    return find_group(RC_XML, RC_PATTERNS[key], default, re.S)


def rc_set(key, value):
    sub_group(RC_XML, RC_PATTERNS[key], value, re.S)
    later("openbox")


def ob_themes():
    names = set()
    for base in ("/usr/share/themes", os.path.join(HOME, ".themes"), os.path.join(HOME, ".local/share/themes")):
        for d in glob.glob(os.path.join(base, "*", "openbox-3")):
            names.add(os.path.basename(os.path.dirname(d)))
    return sorted(names, key=str.lower)


# ------------------------------------------------------------------- autostart
KNOWN = {
    "tint2-session": "Barras tint2", "picom": "Compositor picom", "volumeicon": "Icono de volumen",
    "xfce4-clipman": "Gestor de portapapeles", "lxpolkit": "Agente de autorización (PolicyKit)",
    "nitrogen": "Fondo de pantalla (nitrogen)", "rclone-mount.sh": "Montaje rclone",
    "welcome": "Mensaje de bienvenida", "compton": "Compositor compton",
}


def _program(cmd):
    """Programa real de una línea: salta '(sleep N;' y subshells."""
    c = re.sub(r"[ \t]+#.*$", "", cmd).strip().lstrip("(").strip()
    c = re.sub(r"^sleep\s+\d+\s*;\s*", "", c)
    return re.sub(r"\)?[ \t]*&?[ \t]*$", "", c)


def autostart_entries():
    """Líneas de la sección START APPLICATIONS: [{'cmd', 'enabled', 'title', 'desc'}]."""
    lines = read(AUTOSTART).splitlines()
    start = next((i for i, ln in enumerate(lines) if "START APPLICATIONS" in ln), None)
    if start is None:
        return []
    out = []
    for ln in lines[start + 1:]:
        s = ln.strip()
        if not s:
            continue
        if s.startswith(MARK.strip()):
            enabled, cmd = False, s[len(MARK.strip()):].strip()
        elif s.startswith("#"):
            continue
        else:
            enabled, cmd = True, s
        prog = _program(cmd)
        words = prog.split()
        exe = os.path.basename(words[0]) if words else cmd
        name = KNOWN.get(exe)
        if exe == "conky":
            rc = next((w for w in words if w.endswith(".conkyrc")), "")
            name = "Conky: " + (os.path.basename(os.path.dirname(rc)) or "principal")
        comment = re.search(r"[ \t]#[ \t]*(.+)$", cmd)
        out.append({"cmd": cmd, "enabled": enabled, "title": name or exe,
                    "desc": comment.group(1) if comment else prog[:90]})
    return out


def autostart_find(substr):
    return next((e for e in autostart_entries() if substr in e["cmd"]), None)


def autostart_set(cmd, enabled):
    lines = read(AUTOSTART).split("\n")
    for i, ln in enumerate(lines):
        s = ln.strip()
        plain = s[len(MARK.strip()):].strip() if s.startswith(MARK.strip()) else s
        if plain == cmd and (s == cmd or s.startswith(MARK.strip())):
            indent = ln[: len(ln) - len(ln.lstrip())]
            lines[i] = indent + (cmd if enabled else MARK + cmd)
            write(AUTOSTART, "\n".join(lines))
            return
    raise RuntimeError("No encuentro la línea en el autostart")
