#!/usr/bin/python3 -I
"""Ayudante con privilegios para panel-portatil (se lanza con pkexec).

Recibe en argv[1] una lista JSON de operaciones y solo ejecuta las de la lista
blanca de abajo. Nada de comandos arbitrarios.
"""
import json
import os
import re
import subprocess
import sys

SERVICES = {
    "tlp.service", "apache2.service", "postgresql.service", "ollama.service",
    "ssh.service", "x11vnc.service", "bluetooth.service", "earlyoom.service",
    "pcscd.socket", "fstrim.timer", "cron.service",
}
TLP_KEYS = {
    "CPU_SCALING_GOVERNOR_ON_AC", "CPU_SCALING_GOVERNOR_ON_BAT",
    "CPU_BOOST_ON_AC", "CPU_BOOST_ON_BAT", "USB_AUTOSUSPEND",
    "WIFI_PWR_ON_AC", "WIFI_PWR_ON_BAT",
}
LID_VALUES = {"suspend", "lock", "ignore"}
TLP_FILE = "/etc/tlp.d/90-panel.conf"
LOGIND_FILE = "/etc/systemd/logind.conf.d/90-panel.conf"
SYSCTL_FILE = "/etc/sysctl.d/90-panel.conf"
VALUE_RE = re.compile(r"^[A-Za-z0-9_]{1,24}$")


def run(*cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError((r.stderr or r.stdout).strip() or f"{cmd[0]} fallo")


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def op_svc(name, state):
    if name not in SERVICES or state not in ("on", "off"):
        raise ValueError(f"servicio no permitido: {name}")
    if state == "on":
        run("systemctl", "enable", "--now", name)
    else:
        run("systemctl", "disable", "--now", name)


def op_tlp(key, value):
    if key not in TLP_KEYS or not VALUE_RE.match(value):
        raise ValueError(f"ajuste TLP no permitido: {key}={value}")
    cur = {}
    if os.path.exists(TLP_FILE):
        for line in open(TLP_FILE):
            m = re.match(r'^(\w+)="?([^"\n]*)"?$', line.strip())
            if m:
                cur[m.group(1)] = m.group(2)
    cur[key] = value
    write(TLP_FILE, "# Gestionado por panel-portatil\n"
          + "".join(f'{k}="{v}"\n' for k, v in sorted(cur.items())))
    run("tlp", "start")


def op_lid(value):
    if value not in LID_VALUES:
        raise ValueError(f"accion de tapa no permitida: {value}")
    write(LOGIND_FILE, f"[Login]\nHandleLidSwitch={value}\n"
          f"HandleLidSwitchExternalPower={value}\nHandleLidSwitchDocked=ignore\n")
    run("systemctl", "kill", "-s", "HUP", "systemd-logind")


def op_swappiness(value):
    n = int(value)
    if not 0 <= n <= 100:
        raise ValueError("swappiness fuera de rango")
    write(SYSCTL_FILE, f"vm.swappiness = {n}\n")
    run("sysctl", "-w", f"vm.swappiness={n}")


def op_aptclean():
    run("apt-get", "clean")


def op_aptupdate():
    run("apt-get", "update")


def op_journal(size_mb):
    n = int(size_mb)
    if n not in (50, 100, 200, 500):
        raise ValueError("tamano de journal no permitido")
    run("journalctl", f"--vacuum-size={n}M")


OPS = {"svc": op_svc, "tlp": op_tlp, "lid": op_lid, "swappiness": op_swappiness,
       "aptclean": op_aptclean, "aptupdate": op_aptupdate, "journal": op_journal}


def main():
    ops = json.loads(sys.argv[1])
    errors = []
    for op in ops:
        try:
            OPS[op[0]](*op[1:])
        except Exception as e:  # seguimos con el resto y lo contamos al final
            errors.append(f"{op[0]}: {e}")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
