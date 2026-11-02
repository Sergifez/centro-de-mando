"""Definición de todos los ajustes del panel, agrupados por categoría.

Cada ajuste es un objeto S con get()/set(). Los que necesitan root declaran
`root=lambda v: [op, ...]` y se ejecutan vía root_helper.py con pkexec.
"""
import glob
import json
import os
import re
import shutil
import subprocess

import deskcfg as dc

HERE = os.path.dirname(os.path.abspath(__file__))
HELPER = os.path.join(HERE, "root_helper.py")
STATE_DIR = os.path.expanduser("~/.config/panel-portatil")
STATE_FILE = os.path.join(STATE_DIR, "state.json")
SNAP_FILE = os.path.join(STATE_DIR, "preset-snapshot.json")


# ---------------------------------------------------------------- utilidades
def sh(*cmd, timeout=5):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def check(*cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    if r.returncode:
        raise RuntimeError((r.stderr or r.stdout).strip() or f"{cmd[0]} falló")


def read(path, default=""):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default


def have(cmd):
    return shutil.which(cmd) is not None


def run_root(ops):
    """Ejecuta una lista de operaciones con privilegios (una sola contraseña)."""
    r = subprocess.run(["pkexec", "/usr/bin/python3", "-I", HELPER, json.dumps(ops)],
                       capture_output=True, text=True)
    if r.returncode == 126:
        raise RuntimeError("Autorización cancelada")
    if r.returncode:
        raise RuntimeError(r.stderr.strip() or "Error en el ayudante root")


def load_state():
    try:
        return json.load(open(STATE_FILE))
    except (OSError, ValueError):
        return {}


def save_state(st):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(st, f, indent=1)


class S:
    def __init__(self, id, cat, title, desc, kind, get=None, set=None, root=None,
                 options=None, rng=(0, 100), unit="", persist=False, avail=None,
                 label="Abrir"):
        self.id, self.cat, self.title, self.desc, self.kind = id, cat, title, desc, kind
        self.get, self.set, self.root = get, set, root
        self.options, self.rng, self.unit = options or [], rng, unit
        self.persist, self.avail, self.label = persist, avail, label

    def available(self):
        return self.avail() if self.avail else True

    def apply(self, v):
        dc.begin()
        try:
            if self.root:
                run_root(self.root(v))
            elif self.set:
                self.set(v)
            if self.persist:
                st = load_state()
                st[self.id] = v
                save_state(st)
        finally:
            dc.end()

    def display(self, v):
        if self.kind == "toggle":
            return "Activado" if v else "Desactivado"
        if self.kind == "choice":
            return dict(self.options).get(v, str(v))
        return f"{v}{self.unit}"


# --------------------------------------------------------------------- TLP
def _tlp_value(key):
    for path in ("/etc/tlp.d/90-panel.conf",):
        for line in read(path).splitlines():
            m = re.match(rf'^{key}="?([^"]*)"?$', line.strip())
            if m:
                return m.group(1)
    for path in sorted(glob.glob("/etc/tlp.d/*.conf")) + ["/etc/tlp.conf"]:
        for line in read(path).splitlines():
            m = re.match(rf'^{key}="?([^"]*)"?', line.strip())
            if m:
                return m.group(1)
    for line in read("/usr/share/tlp/defaults.conf").splitlines():
        m = re.match(rf'^{key}="?([^"]*)"?', line.strip())
        if m:
            return m.group(1)
    return ""


def tlp_choice(id, title, desc, key, options):
    return S(id, "energia", title, desc, "choice", options=options,
             get=lambda: _tlp_value(key), root=lambda v: [["tlp", key, v]])


def tlp_toggle(id, title, desc, key, on="1", off="0", fallback=None):
    def get():
        v = _tlp_value(key)
        if v == "" and fallback:
            return fallback()
        return v == on
    return S(id, "energia", title, desc, "toggle", get=get,
             root=lambda v: [["tlp", key, on if v else off]])


def svc_active(name):
    return sh("systemctl", "is-active", name).strip() in ("active", "listening", "waiting")


def svc_toggle(id, cat, title, desc, unit):
    return S(id, cat, title, desc, "toggle", get=lambda: svc_active(unit),
             root=lambda v: [["svc", unit, "on" if v else "off"]],
             avail=lambda: bool(sh("systemctl", "list-unit-files", unit).count(unit)))


def _turbo_now():
    return read("/sys/devices/system/cpu/intel_pstate/no_turbo", "0") == "0"


def _lid_get():
    m = re.search(r"HandleLidSwitch=(\w+)", read("/etc/systemd/logind.conf.d/90-panel.conf"))
    return m.group(1) if m else "suspend"


# ----------------------------------------------------------------- pantalla
def _brightness_get():
    out = sh("brightnessctl", "-m").split(",")
    return int(out[3].rstrip("%")) if len(out) > 3 else 50


def _output():
    for line in sh("xrandr").splitlines():
        if " connected" in line:
            return line.split()[0]
    return "eDP-1"


def _modes():
    modes, on = [], False
    for line in sh("xrandr").splitlines():
        if line.startswith(_output() + " "):
            on = True
        elif on and line.startswith("   "):
            modes.append(line.split()[0])
        elif on:
            break
    return modes


def _mode_get():
    on = False
    for line in sh("xrandr").splitlines():
        if line.startswith(_output() + " "):
            on = True
        elif on and "*" in line:
            return line.split()[0]
    return ""


def _picom_set(v):
    if v:
        subprocess.Popen(["picom", "--backend", "xrender"], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        check("pkill", "-x", "picom")


GAMMAS = [("1:1:1", "Normal"), ("1:0.92:0.8", "Cálido"), ("1:0.82:0.6", "Noche"),
          ("1:0.7:0.45", "Muy cálido")]


def _dpms_get():
    q = sh("xset", "q")
    if "DPMS is Disabled" in q:
        return "0"
    m = re.search(r"Off:\s+(\d+)", q)
    return str(int(m.group(1)) // 60) if m else "0"


def _dpms_set(v):
    n = int(v)
    if n == 0:
        check("xset", "-dpms")
    else:
        check("xset", "+dpms")
        check("xset", "dpms", "0", "0", str(n * 60))
    check("xset", "s", "off")


# -------------------------------------------------------------------- audio
def _vol_get():
    m = re.search(r"Volume:\s+([\d.]+)", sh("wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"))
    return round(float(m.group(1)) * 100) if m else 0


def _muted(target):
    return "MUTED" in sh("wpctl", "get-volume", target)


# -------------------------------------------------------------------- entrada
def _tp_name():
    for n in sh("xinput", "list", "--name-only").splitlines():
        if "touchpad" in n.lower():
            return n.strip()
    return None


def _prop(name, prop):
    for line in sh("xinput", "list-props", name).splitlines():
        if prop + " (" in line:
            return line.split(":", 1)[1].strip().split(",")[0].strip()
    return None


def _prop_set(name, prop, val):
    check("xinput", "set-prop", name, prop, str(val))


def tp_toggle(id, title, desc, prop):
    def get():
        n = _tp_name()
        return bool(n and _prop(n, prop) == "1")
    return S(id, "entrada", title, desc, "toggle", get=get, persist=True,
             set=lambda v: _prop_set(_tp_name(), prop, int(v)), avail=lambda: _tp_name() is not None)


def _tp_enabled():
    n = _tp_name()
    return bool(n and _prop(n, "Device Enabled") == "1")


def _tp_enable(v):
    check("xinput", "enable" if v else "disable", _tp_name())


def _accel_get():
    n = _tp_name()
    try:
        return round(float(_prop(n, "libinput Accel Speed")) * 100)
    except (TypeError, ValueError):
        return 0


def _layout_get():
    m = re.search(r"layout:\s+(\S+)", sh("setxkbmap", "-query"))
    return m.group(1).split(",")[0] if m else ""


def _repeat_get(which):
    m = re.search(r"auto repeat delay:\s+(\d+)\s+repeat rate:\s+(\d+)", sh("xset", "q"))
    return int(m.group(which)) if m else 0


def _repeat_set(which, v):
    d, r = _repeat_get(1), _repeat_get(2)
    if which == 1:
        d = v
    else:
        r = v
    check("xset", "r", "rate", str(d), str(r))


# ------------------------------------------------------------------ escritorio
def launcher(id, title, desc, cmd, label="Abrir", cat="escritorio"):
    return S(id, cat, title, desc, "button", label=label, avail=lambda: have(cmd[0]),
             set=lambda _v: subprocess.Popen(cmd, start_new_session=True,
                                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))


def _autostart_entries():
    out = []
    for path in sorted(glob.glob(os.path.expanduser("~/.config/autostart/*.desktop"))):
        txt = read(path)
        name = re.search(r"^Name=(.+)$", txt, re.M)
        comment = re.search(r"^Comment=(.+)$", txt, re.M)
        out.append((path, name.group(1) if name else os.path.basename(path),
                    comment.group(1) if comment else os.path.basename(path)))
    return out


def _autostart_on(path):
    txt = read(path)
    return not re.search(r"^Hidden=true", txt, re.M) and \
        not re.search(r"^X-GNOME-Autostart-enabled=false", txt, re.M)


def _autostart_set(path, v):
    lines = [ln for ln in read(path).splitlines() if not ln.startswith("Hidden=")]
    lines.append("Hidden=" + ("false" if v else "true"))
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def autostart_settings():
    res = []
    for path, name, comment in _autostart_entries():
        res.append(S("autostart:" + os.path.basename(path), "arranque", f"Sesión XDG: {name}",
                     comment, "toggle", get=lambda p=path: _autostart_on(p),
                     set=lambda v, p=path: _autostart_set(p, v)))
    return res


# ------------------------------------------------------------------ personalización
CONKYS = [("grapes", "Monitor conky-grapes", "~/.config/conky/conky-grapes/conky_gen.conkyrc"),
          ("atajos", "Chuleta de atajos", "~/.config/conky/atajos/atajos.conkyrc")]
ALIGN = [("top_left", "Arriba izquierda"), ("top_middle", "Arriba centro"), ("top_right", "Arriba derecha"),
         ("middle_middle", "Centro"), ("bottom_left", "Abajo izquierda"), ("bottom_middle", "Abajo centro"),
         ("bottom_right", "Abajo derecha")]


def _conky_run_set(rc, v):
    dc.conky_stop(rc)
    if v:
        dc.conky_start(rc)


def _boot_toggle(id, cat, title, desc, substr):
    def sett(v):
        e = dc.autostart_find(substr)
        dc.autostart_set(e["cmd"], v)
    return S(id, cat, title, desc, "toggle", get=lambda: bool((dc.autostart_find(substr) or {}).get("enabled")),
             set=sett, avail=lambda: dc.autostart_find(substr) is not None)


def conky_settings():
    items = []
    for key, name, rc in CONKYS:
        rc = os.path.expanduser(rc)
        ok = lambda rc=rc: os.path.exists(rc)
        items += [
            S(f"cky_{key}_run", "conky", name, "Mostrar u ocultar ahora mismo en el escritorio.", "toggle",
              get=lambda rc=rc: bool(dc.conky_pids(rc)), set=lambda v, rc=rc: _conky_run_set(rc, v),
              avail=lambda ok=ok: ok() and have("conky")),
            _boot_toggle(f"cky_{key}_boot", "conky", f"{name}: al iniciar sesión",
                         "Arrancarlo automáticamente al entrar (línea del autostart).", os.path.basename(rc)),
            S(f"cky_{key}_al", "conky", f"{name}: posición", "Esquina o zona del escritorio donde se ancla.",
              "choice", options=ALIGN, get=lambda rc=rc: dc.lua_get(rc, "alignment", "top_left"),
              set=lambda v, rc=rc: (dc.lua_set(rc, "alignment", v, quote=True), dc.later(("conky", rc))),
              avail=ok),
            S(f"cky_{key}_x", "conky", f"{name}: margen horizontal", "Separación del borde lateral (px).",
              "slider", rng=(-400, 1400), unit=" px", get=lambda rc=rc: int(dc.lua_get(rc, "gap_x", "0")),
              set=lambda v, rc=rc: (dc.lua_set(rc, "gap_x", v), dc.later(("conky", rc))), avail=ok),
            S(f"cky_{key}_y", "conky", f"{name}: margen vertical", "Separación del borde superior o inferior (px).",
              "slider", rng=(-400, 800), unit=" px", get=lambda rc=rc: int(dc.lua_get(rc, "gap_y", "0")),
              set=lambda v, rc=rc: (dc.lua_set(rc, "gap_y", v), dc.later(("conky", rc))), avail=ok),
        ]
    return items


def _taskbar_options():
    names = {"taskbar": "Principal", "taskbar_laptop": "Portátil", "taskbar_win": "Estilo Windows"}
    opts = [(n, names.get(n, n)) for n in sorted(dc.tint_variants())]
    return opts + [("", "Ninguna")]


def _taskbar_get():
    return next((n for n, on in dc.tint_variants().items() if on), "")


def _tint_key(id, title, desc, key, kind="toggle", options=None, rng=(0, 100), on="1", off="0"):
    def path():
        return dc.tint_active_taskbar()
    def getter():
        v = dc.ini_get(path(), key)
        return (v == on) if kind == "toggle" else v
    def setter(v):
        dc.ini_set(path(), key, (on if v else off) if kind == "toggle" else v)
        dc.later("tint2")
    return S(id, "barras", title, desc, kind, options=options, get=getter, set=setter,
             avail=lambda: path() is not None)


def tint_settings():
    def h_get():
        m = re.search(r"\d+%?\s+(\d+)", dc.ini_get(dc.tint_active_taskbar(), "panel_size"))
        return int(m.group(1)) if m else 38

    def h_set(v):
        cur = dc.ini_get(dc.tint_active_taskbar(), "panel_size")
        w = cur.split()[0] if cur else "100%"
        dc.ini_set(dc.tint_active_taskbar(), "panel_size", f"{w} {v}")
        dc.later("tint2")

    return [
        S("tint_bar", "barras", "Barra de tareas", "Qué configuración de barra inferior se carga.", "choice",
          options=_taskbar_options(), get=_taskbar_get, set=dc.tint_set_taskbar,
          avail=lambda: bool(dc.tint_variants())),
        S("tint_menu", "barras", "Barra del menú (superior)", "Barra fina con el menú de aplicaciones.", "toggle",
          get=dc.tint_menu_on, set=dc.tint_set_menu,
          avail=lambda: os.path.exists(os.path.join(dc.TINT_DIR, "menu.tint2rc"))
          or os.path.exists(os.path.join(dc.TINT_DIR, "menu.tint2rc_"))),
        _tint_key("tint_pos", "Posición de la barra", "Arriba o abajo del escritorio.", "panel_position",
                  kind="choice", options=[("bottom center horizontal", "Abajo"), ("top center horizontal", "Arriba")]),
        S("tint_h", "barras", "Altura de la barra", "Alto de la barra de tareas en píxeles.", "slider",
          rng=(24, 64), unit=" px", get=h_get, set=h_set, avail=lambda: dc.tint_active_taskbar() is not None),
        _tint_key("tint_hide", "Ocultar automáticamente", "La barra se esconde cuando no la usas.", "autohide"),
        _tint_key("tint_clock", "Formato del reloj", "24 horas o 12 horas con AM/PM.", "time1_format",
                  kind="choice", options=[("%H:%M", "24 horas"), ("%I:%M %p", "12 horas")]),
        _tint_key("tint_date", "Fecha bajo el reloj", "Segunda línea del reloj.", "time2_format",
                  kind="choice", options=[("", "Sin fecha"), ("%d/%m/%Y", "31/12/2026"), ("%a %d %b", "Lun 31 dic")]),
        _tint_key("tint_taskmode", "Ventanas en la barra", "Qué ventanas se muestran en la barra de tareas.",
                  "taskbar_mode", kind="choice",
                  options=[("multi_desktop", "De todos los escritorios"), ("single_desktop", "Solo del escritorio actual")]),
    ]


def picom_settings():
    def b(key, default="false"):
        return lambda: dc.picom_get(key, default) == "true"
    pr = dc.PICOM_CONF
    return [
        S("pc_shadow", "compositor", "Sombras", "Sombra bajo las ventanas.", "toggle", get=b("shadow"),
          set=lambda v: dc.picom_set("shadow", "true" if v else "false"), avail=lambda: have("picom")),
        S("pc_fade", "compositor", "Fundidos", "Animación suave al abrir y cerrar ventanas.", "toggle",
          get=b("fading"), set=lambda v: dc.picom_set("fading", "true" if v else "false"), avail=lambda: have("picom")),
        S("pc_vsync", "compositor", "Sincronización vertical", "Evita cortes (tearing) a costa de algo de latencia.",
          "toggle", get=b("vsync", "true"), set=lambda v: dc.picom_set("vsync", "true" if v else "false"),
          avail=lambda: have("picom")),
        S("pc_inact", "compositor", "Opacidad de ventanas inactivas", "100 % = sin transparencia.", "slider",
          rng=(30, 100), unit="%", get=lambda: round(float(dc.picom_get("inactive-opacity", "1")) * 100),
          set=lambda v: dc.picom_set("inactive-opacity", f"{v / 100:.2f}"), avail=lambda: have("picom")),
        S("pc_conky", "compositor", "Opacidad de la chuleta de atajos", "Transparencia del conky de atajos.",
          "slider", rng=(5, 100), unit="%", get=dc.conky_opacity_get, set=dc.conky_opacity_set,
          avail=lambda: have("picom")),
    ]


LAYOUTS = [("DSLIMC", "Por defecto"), ("NLIMC", "Con icono de la app"), ("LIMC", "Sencillo"),
           ("CIML", "Botones a la izquierda")]


def window_settings():
    ok = lambda: os.path.exists(dc.RC_XML)
    themes = [(t, t) for t in dc.ob_themes()]
    return [
        S("ob_theme", "ventanas", "Tema de ventanas", "Aspecto de los marcos y la barra de título de Openbox.",
          "choice", options=themes, get=lambda: dc.rc_get("theme"), set=lambda v: dc.rc_set("theme", v), avail=ok),
        S("ob_layout", "ventanas", "Botones de la barra de título", "Orden y botones que aparecen en cada ventana.",
          "choice", options=LAYOUTS, get=lambda: dc.rc_get("layout"), set=lambda v: dc.rc_set("layout", v), avail=ok),
        S("ob_desk", "ventanas", "Número de escritorios", "Escritorios virtuales al iniciar sesión.", "slider",
          rng=(1, 8), get=lambda: int(dc.rc_get("desktops", "2")), set=lambda v: dc.rc_set("desktops", v), avail=ok),
        S("ob_follow", "ventanas", "El foco sigue al ratón", "La ventana bajo el puntero recibe el foco sin clic.",
          "toggle", get=lambda: dc.rc_get("follow") == "yes",
          set=lambda v: dc.rc_set("follow", "yes" if v else "no"), avail=ok),
    ]


def boot_settings():
    items = []
    for i, e in enumerate(dc.autostart_entries()):
        cmd = e["cmd"]
        items.append(S(f"boot:{i}", "arranque", e["title"], e["desc"] + "  · autostart de Openbox", "toggle",
                       get=lambda cmd=cmd: next((x["enabled"] for x in dc.autostart_entries() if x["cmd"] == cmd), False),
                       set=lambda v, cmd=cmd: dc.autostart_set(cmd, v)))
    return items


# ----------------------------------------------------------------------- nube
DRIVE = os.path.expanduser("~/Drive")
MOUNT_SCRIPT = os.path.expanduser("~/.config/rclone-mount.sh")


def _drive_mounted():
    return subprocess.run(["mountpoint", "-q", DRIVE]).returncode == 0


def _drive_set(v):
    if v:
        if not os.path.exists(MOUNT_SCRIPT):
            raise RuntimeError("Falta ~/.config/rclone-mount.sh")
        r = subprocess.run(["bash", MOUNT_SCRIPT], capture_output=True, text=True, timeout=200)
        if r.returncode:
            raise RuntimeError("No se pudo montar Drive (¿hay red?). Mira el registro de rclone.")
    else:
        for tool in ("fusermount3", "fusermount"):
            if have(tool):
                check(tool, "-u", DRIVE)
                return
        raise RuntimeError("No hay fusermount para desmontar")


def cloud_settings():
    terminal = lambda cmd: subprocess.Popen(["x-terminal-emulator", "-e", "bash", "-c", cmd], start_new_session=True)
    return [
        S("drive_on", "nube", "Unidad Google Drive", "Monta o desmonta ~/Drive con rclone (montarla puede tardar si no hay red).",
          "toggle", get=_drive_mounted, set=_drive_set, avail=lambda: have("rclone")),
        _boot_toggle("drive_boot", "nube", "Montar al iniciar sesión", "Línea rclone-mount.sh del autostart de Openbox.",
                     "rclone-mount.sh"),
        S("drive_open", "nube", "Abrir carpeta Drive", "Abre ~/Drive en el gestor de archivos.", "button",
          avail=lambda: os.path.isdir(DRIVE),
          set=lambda _v: subprocess.Popen(["xdg-open", DRIVE], start_new_session=True)),
        S("drive_log", "nube", "Ver registro de rclone", "Últimas líneas de ~/.cache/rclone/mount.log en una terminal.",
          "button", label="Ver", avail=lambda: os.path.exists(os.path.expanduser("~/.cache/rclone/mount.log")),
          set=lambda _v: terminal("tail -n 60 ~/.cache/rclone/mount.log; echo; read -rp 'Pulsa Intro…'")),
    ]


# --------------------------------------------------------------------- tabla
CATEGORIES = [
    # (id, nombre, grupo, icono)
    ("resumen", "Resumen", "GENERAL", "◉"),
    ("presets", "Presets", "GENERAL", "☰"),
    ("ayuda", "Ayuda", "GENERAL", "?"),
    ("energia", "Energía", "HARDWARE", "⚡"),
    ("pantalla", "Pantalla", "HARDWARE", "▭"),
    ("audio", "Audio", "HARDWARE", "♪"),
    ("entrada", "Entrada", "HARDWARE", "⌨"),
    ("bateria", "Batería", "HARDWARE", "▮"),
    ("red", "Red", "CONECTIVIDAD", "≋"),
    ("nube", "Nube (Drive)", "CONECTIVIDAD", "☁"),
    ("escritorio", "Escritorio", "PERSONALIZACIÓN", "▦"),
    ("conky", "Conky", "PERSONALIZACIÓN", "◔"),
    ("barras", "Barras tint2", "PERSONALIZACIÓN", "▬"),
    ("compositor", "Compositor", "PERSONALIZACIÓN", "◐"),
    ("ventanas", "Ventanas", "PERSONALIZACIÓN", "❐"),
    ("arranque", "Arranque", "PERSONALIZACIÓN", "⏻"),
    ("atajos", "Atajos", "PERSONALIZACIÓN", "⌘"),
    ("archivos", "Archivos", "PERSONALIZACIÓN", "✎"),
    ("servicios", "Servicios", "SISTEMA", "⚙"),
    ("sistema", "Sistema", "SISTEMA", "▤"),
    ("actualizaciones", "Actualizaciones", "SISTEMA", "⟳"),
    ("disco", "Disco", "SISTEMA", "◙"),
    ("procesos", "Procesos", "SISTEMA", "≣"),
    ("apps", "Apps", "SISTEMA", "▣"),
    ("dotfiles", "Dotfiles", "SISTEMA", "⎇"),
]

GOVS = [("powersave", "Ahorro (powersave)"), ("performance", "Rendimiento (performance)")]
MIN = [("0", "Nunca"), ("1", "1 minuto"), ("2", "2 minutos"), ("5", "5 minutos"),
       ("10", "10 minutos"), ("15", "15 minutos"), ("30", "30 minutos")]


def build():
    st = load_state()
    items = [
        # ---- energía
        svc_toggle("tlp", "energia", "Gestión de energía TLP",
                   "Servicio que aplica los ajustes de ahorro de esta sección.", "tlp.service"),
        tlp_choice("gov_bat", "CPU con batería", "Gobernador de frecuencia al ir con batería.",
                   "CPU_SCALING_GOVERNOR_ON_BAT", GOVS),
        tlp_choice("gov_ac", "CPU con corriente", "Gobernador de frecuencia al ir enchufado.",
                   "CPU_SCALING_GOVERNOR_ON_AC", GOVS),
        tlp_toggle("boost_bat", "Turbo con batería", "Permite subir frecuencia por encima de la base.",
                   "CPU_BOOST_ON_BAT", fallback=_turbo_now),
        tlp_toggle("usb_auto", "Suspensión automática USB",
                   "Apaga puertos USB inactivos; puede dar tirones en ratones.", "USB_AUTOSUSPEND"),
        tlp_choice("wifi_bat", "Ahorro Wi-Fi con batería", "Reduce potencia de la tarjeta Wi-Fi.",
                   "WIFI_PWR_ON_BAT", [("on", "Activado"), ("off", "Desactivado")]),
        S("lid", "energia", "Al cerrar la tapa", "Acción del sistema al cerrar la tapa del portátil.",
          "choice", options=[("suspend", "Suspender"), ("lock", "Bloquear"), ("ignore", "No hacer nada")],
          get=_lid_get, root=lambda v: [["lid", v]]),
        S("dpms", "energia", "Apagar pantalla por inactividad", "Tiempo sin actividad antes de apagar la pantalla.",
          "choice", options=MIN, get=_dpms_get, set=_dpms_set, persist=True),
        # ---- pantalla
        S("brillo", "pantalla", "Brillo", "Brillo de la retroiluminación.", "slider", rng=(5, 100),
          unit="%", get=_brightness_get, avail=lambda: have("brightnessctl"),
          set=lambda v: check("brightnessctl", "set", f"{v}%")),
        S("picom", "pantalla", "Compositor (picom)", "Transparencias y sombras. Apagarlo ahorra CPU.",
          "toggle", get=lambda: bool(sh("pgrep", "-x", "picom").strip()), set=_picom_set,
          avail=lambda: have("picom")),
        S("gamma", "pantalla", "Temperatura de color", "Tinte cálido para reducir luz azul por la noche.",
          "choice", options=GAMMAS, get=lambda: load_state().get("gamma", "1:1:1"), persist=True,
          set=lambda v: check("xrandr", "--output", _output(), "--gamma", v)),
        S("modo", "pantalla", "Resolución", "Resolución de la pantalla integrada.", "choice",
          options=[(m, m) for m in _modes()], get=_mode_get,
          set=lambda v: check("xrandr", "--output", _output(), "--mode", v)),
        # ---- audio
        S("vol", "audio", "Volumen de salida", "Volumen de la salida por defecto (PipeWire).", "slider",
          unit="%", get=_vol_get, avail=lambda: have("wpctl"),
          set=lambda v: check("wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{v}%")),
        S("mute", "audio", "Silenciar salida", "Silencia la salida por defecto.", "toggle",
          get=lambda: _muted("@DEFAULT_AUDIO_SINK@"), avail=lambda: have("wpctl"),
          set=lambda v: check("wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "1" if v else "0")),
        S("micmute", "audio", "Silenciar micrófono", "Silencia la entrada por defecto.", "toggle",
          get=lambda: _muted("@DEFAULT_AUDIO_SOURCE@"), avail=lambda: have("wpctl"),
          set=lambda v: check("wpctl", "set-mute", "@DEFAULT_AUDIO_SOURCE@", "1" if v else "0")),
        S("mesa", "audio", "Mesa de sonido ZENIT-8", "Mezclador de 8 canales con efectos y EQ.", "button",
          avail=lambda: have("mesa-sonido"),
          set=lambda _v: subprocess.Popen(["mesa-sonido"], start_new_session=True)),
        S("pavu", "audio", "Mezclador de volúmenes", "Control por aplicación y dispositivos.", "button",
          avail=lambda: have("pavucontrol"),
          set=lambda _v: subprocess.Popen(["pavucontrol"], start_new_session=True)),
        # ---- entrada
        S("tp_on", "entrada", "Touchpad", "Activa o desactiva el touchpad.", "toggle", get=_tp_enabled,
          set=_tp_enable, avail=lambda: _tp_name() is not None, persist=True),
        tp_toggle("tp_tap", "Tocar para hacer clic", "Un toque en el touchpad equivale a un clic.",
                  "libinput Tapping Enabled"),
        tp_toggle("tp_nat", "Desplazamiento natural", "El contenido sigue a los dedos, como en un móvil.",
                  "libinput Natural Scrolling Enabled"),
        tp_toggle("tp_dwt", "Ignorar al escribir", "Desactiva el touchpad mientras tecleas.",
                  "libinput Disable While Typing Enabled"),
        S("tp_acc", "entrada", "Velocidad del puntero", "Sensibilidad del touchpad (−100 a 100).", "slider",
          rng=(-100, 100), get=_accel_get, persist=True, avail=lambda: _tp_name() is not None,
          set=lambda v: _prop_set(_tp_name(), "libinput Accel Speed", v / 100)),
        S("layout", "entrada", "Distribución de teclado", "Idioma del teclado en esta sesión.", "choice",
          options=[("es", "Español"), ("us", "Inglés (US)"), ("gb", "Inglés (UK)"), ("fr", "Francés"),
                   ("de", "Alemán"), ("latam", "Latinoamérica")],
          get=_layout_get, persist=True, set=lambda v: check("setxkbmap", v)),
        S("rep_delay", "entrada", "Retardo de repetición", "Milisegundos antes de repetir una tecla.",
          "slider", rng=(150, 1000), unit=" ms", get=lambda: _repeat_get(1), persist=True,
          set=lambda v: _repeat_set(1, v)),
        S("rep_rate", "entrada", "Velocidad de repetición", "Repeticiones por segundo.", "slider",
          rng=(5, 60), unit="/s", get=lambda: _repeat_get(2), persist=True,
          set=lambda v: _repeat_set(2, v)),
        # ---- red
        S("wifi", "red", "Wi-Fi", "Radio inalámbrica.", "toggle", avail=lambda: have("nmcli"),
          get=lambda: sh("nmcli", "radio", "wifi").strip() == "enabled",
          set=lambda v: check("nmcli", "radio", "wifi", "on" if v else "off")),
        S("bt", "red", "Bluetooth", "Radio Bluetooth (rfkill).", "toggle", avail=lambda: have("rfkill"),
          get=lambda: "Soft blocked: no" in sh("rfkill", "list", "bluetooth"),
          set=lambda v: check("rfkill", "unblock" if v else "block", "bluetooth")),
        launcher("nm", "Editor de conexiones", "Redes, VPN y DNS de NetworkManager.",
                 ["nm-connection-editor"], cat="red"),
        # ---- escritorio
        launcher("lxa", "Apariencia", "Tema GTK, iconos y fuentes.", ["lxappearance"]),
        launcher("nitro", "Fondo de escritorio", "Elegir el fondo con nitrogen.", ["nitrogen"]),
        launcher("obconf", "Configuración de Openbox", "Temas, ventanas y escritorios.", ["obconf"]),
        launcher("obmenu", "Editor del menú", "Editar el menú de clic derecho.", ["openbox-menu-editor"]),
        S("obrecon", "escritorio", "Recargar Openbox", "Aplica cambios de rc.xml y del menú.", "button",
          label="Recargar", set=lambda _v: check("openbox", "--reconfigure")),
        # ---- servicios
        svc_toggle("s_apache", "servicios", "Apache", "Servidor web.", "apache2.service"),
        svc_toggle("s_pg", "servicios", "PostgreSQL", "Base de datos.", "postgresql.service"),
        svc_toggle("s_ollama", "servicios", "Ollama", "Modelos de lenguaje locales (consume RAM).",
                   "ollama.service"),
        svc_toggle("s_ssh", "servicios", "SSH", "Acceso remoto por terminal.", "ssh.service"),
        svc_toggle("s_vnc", "servicios", "x11vnc", "Escritorio remoto por VNC.", "x11vnc.service"),
        svc_toggle("s_bt", "servicios", "Servicio Bluetooth", "Demonio bluetoothd.", "bluetooth.service"),
        svc_toggle("s_oom", "servicios", "earlyoom", "Mata procesos antes de quedarse sin memoria.",
                   "earlyoom.service"),
        svc_toggle("s_pcsc", "servicios", "Lector de tarjetas (pcscd)", "Necesario para el DNIe.",
                   "pcscd.socket"),
        # ---- sistema
        S("swap", "sistema", "Swappiness", "Cuánto prefiere el kernel usar swap (0 = casi nunca, 100 = mucho).",
          "slider", rng=(0, 100), get=lambda: int(read("/proc/sys/vm/swappiness", "60")),
          root=lambda v: [["swappiness", int(v)]]),
        svc_toggle("trim", "sistema", "TRIM semanal del disco", "Mantiene el rendimiento del SSD.",
                   "fstrim.timer"),
        svc_toggle("cron", "sistema", "Tareas programadas (cron)", "Ejecuta las tareas de crontab.",
                   "cron.service"),
    ]
    items = [i for i in items if i is not None]
    items += conky_settings() + tint_settings() + picom_settings() + window_settings() + boot_settings() + cloud_settings()
    items += autostart_settings()
    return items


PRESETS = [
    ("ahorro", "Ahorro", "Máxima autonomía: brillo bajo, sin compositor, Bluetooth apagado.",
     {"brillo": 35, "picom": False, "bt": False, "gov_bat": "powersave", "boost_bat": False,
      "usb_auto": True, "wifi_bat": "on", "dpms": "2"}),
    ("equilibrado", "Equilibrado", "Uso diario: brillo medio y turbo disponible.",
     {"brillo": 60, "picom": True, "gov_bat": "powersave", "boost_bat": True, "usb_auto": True,
      "wifi_bat": "on", "dpms": "5"}),
    ("rendimiento", "Rendimiento", "Todo a tope: brillo máximo y CPU sin límites.",
     {"brillo": 100, "picom": True, "gov_ac": "performance", "gov_bat": "performance",
      "boost_bat": True, "usb_auto": False, "wifi_bat": "off", "dpms": "15"}),
]


def apply_many(items, changes):
    """Aplica {id: valor}; agrupa todas las operaciones root en una sola autorización."""
    by_id = {s.id: s for s in items}
    root_ops, errors = [], []
    dc.begin()
    for id, v in changes.items():
        s = by_id.get(id)
        if not s or not s.available():
            continue
        try:
            if s.root:
                root_ops += s.root(v)
            else:
                s.apply(v)
        except Exception as e:
            errors.append(f"{s.title}: {e}")
    if root_ops:
        try:
            run_root(root_ops)
        except Exception as e:
            errors.append(str(e))
    try:
        dc.end()  # una sola recarga de tint2/picom/openbox/conky para todo el lote
    except Exception as e:
        errors.append(str(e))
    if errors:
        raise RuntimeError("\n".join(errors))


def apply_saved():
    """Reaplica los ajustes de sesión (xinput, xset, gamma…). Para el autostart."""
    items = {s.id: s for s in build()}
    for id, v in load_state().items():
        s = items.get(id)
        if s and s.set and s.available():
            try:
                s.set(v)
            except Exception:
                pass
