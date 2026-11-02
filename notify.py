"""Avisos de escritorio (notify-send) desde el panel residente en la bandeja.

Cada aviso se lanza UNA vez al cumplirse la condición y se rearma cuando vuelve a la normalidad
(con histéresis), para no repetirse cada medio minuto.
"""
import json
import os
import subprocess
import time

from PyQt6.QtCore import QObject, QTimer

import apps

PREFS = os.path.expanduser("~/.config/panel-portatil/prefs.json")
CHECK_EVERY = 12 * 3600   # comprobación de actualizaciones de AppImage (segundos)


def load_prefs():
    try:
        return json.load(open(PREFS))
    except (OSError, ValueError):
        return {}


def save_prefs(p):
    os.makedirs(os.path.dirname(PREFS), exist_ok=True)
    json.dump(p, open(PREFS, "w"), indent=1)


def enabled():
    return load_prefs().get("notify", True)


def set_enabled(on):
    p = load_prefs()
    p["notify"] = bool(on)
    save_prefs(p)


def send(title, body, urgency="normal", icon="dialog-information", timeout=10000):
    try:
        subprocess.Popen(["notify-send", "-a", "Centro de mando", "-u", urgency, "-i", icon,
                          "-t", str(timeout), title, body], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def evaluate(s, active):
    """s: dict(cap, status, temp, disk). active: conjunto de avisos ya lanzados (se modifica).
    → lista de (title, body, urgency, icon) nuevos."""
    out = []

    def edge(key, cond, rearm, msg):
        if cond and key not in active:
            active.add(key)
            out.append(msg)
        elif key in active and rearm:
            active.discard(key)

    cap, dis = s.get("cap"), s.get("status") == "Discharging"
    if cap is not None:
        edge("bat-crit", dis and cap <= 10, not dis or cap > 15,
             ("Batería crítica", f"Queda un {cap} %. Conecta el cargador ya o el equipo se apagará.",
              "critical", "battery-caution"))
        edge("bat-low", dis and 10 < cap <= 20, not dis or cap > 25,
             ("Batería baja", f"Queda un {cap} %. Conviene conectar el cargador.", "normal", "battery-low"))
    t = s.get("temp")
    if t is not None:
        edge("cpu-hot", t >= 85, t < 78,
             ("CPU muy caliente", f"{t} °C. Cierra procesos pesados o usa el preset Ahorro.", "critical",
              "dialog-warning"))
    d = s.get("disk")
    if d is not None:
        edge("disk", d >= 90, d < 85,
             ("Disco casi lleno", f"La raíz está al {d} %. Libera espacio en Disco ▸ Limpieza.", "normal",
              "drive-harddisk"))
    return out


# ---------------------------------------------------------- actualizaciones de apps


class Alerts(QObject):
    """Evalúa el estado cada 30 s y avisa. `sample()` devuelve dict(cap, status, temp, disk)."""

    def __init__(self, sample, parent=None):
        super().__init__(parent)
        self.sample = sample
        self.active = set()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(30_000)
        self.checker = None
        QTimer.singleShot(5_000, self.tick)
        QTimer.singleShot(90_000, self.check_apps)   # tras el arranque, sin competir por la red
        self.app_timer = QTimer(self)
        self.app_timer.timeout.connect(self.check_apps)
        self.app_timer.start(CHECK_EVERY * 1000)

    def tick(self):
        try:
            s = self.sample()
        except Exception:
            return
        for title, body, urg, icon in evaluate(s, self.active):
            if enabled():
                send(title, body, urg, icon)

    def check_apps(self):
        """Comprueba AppImage en un hilo; guarda el resultado y avisa de las novedades."""
        if self.checker or not enabled():
            return
        paths = apps.list_apps()

        def work(_emit):
            return {p: apps.check_update(p) for p in paths}

        self.checker = apps.Worker(work)
        self.checker.done.connect(self._checked)
        self.checker.start()

    def _checked(self, res):
        self.checker = None
        if not isinstance(res, dict) or "state" in res:   # fallo del hilo: no tocamos la caché
            return
        cache = apps.load_cache()
        told = set(cache.get("_told", []))
        new = {p: r for p, r in res.items() if r.get("state") == "nueva"}
        fresh = [p for p, r in new.items() if f"{p}|{r.get('label')}" not in told]
        cache = {p: dict(r, checked=int(time.time())) for p, r in res.items()}
        cache["_told"] = sorted(told | {f"{p}|{r.get('label')}" for p, r in new.items()})
        apps.save_cache(cache)
        if fresh and enabled():
            names = ", ".join(apps.pretty_name(p) for p in fresh)
            send("Actualizaciones de aplicaciones",
                 f"{len(fresh)} disponible{'s' if len(fresh) > 1 else ''}: {names}. "
                 "Abre el Centro de mando ▸ Apps para actualizar.", "normal", "software-update-available")
