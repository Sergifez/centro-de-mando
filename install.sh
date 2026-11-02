#!/bin/sh
# Instala el lanzador, la entrada de menú y los iconos del Centro de mando para el usuario actual.
# Uso: ./install.sh        (para quitarlo: ./install.sh --uninstall)
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
BIN="$HOME/.local/bin/panel-portatil"
APPS="$HOME/.local/share/applications"
ICONS="$HOME/.local/share/icons/hicolor/scalable/apps"

if [ "$1" = "--uninstall" ]; then
    rm -f "$BIN" "$APPS/panel-portatil.desktop" "$ICONS/panel-portatil.svg"
    echo "Desinstalado (el código en $DIR no se toca)."
    exit 0
fi

python3 -c "import PyQt6.QtWidgets" 2>/dev/null || {
    echo "Falta PyQt6. En Debian/Ubuntu: sudo apt install python3-pyqt6" >&2
    exit 1
}
mkdir -p "$HOME/.local/bin" "$APPS" "$ICONS"
printf '#!/bin/sh\nexec python3 "%s/panel.py" "$@"\n' "$DIR" > "$BIN"
chmod +x "$BIN"
cp "$DIR/panel-portatil.svg" "$ICONS/panel-portatil.svg"
cat > "$APPS/panel-portatil.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=Centro de mando
Comment=Ajustes y comportamiento del portátil
Exec=$BIN
Icon=panel-portatil
Categories=Settings;System;
DESK
echo "Instalado. Ejecuta: panel-portatil   (o búscalo en el menú: «Centro de mando»)"
echo "Para arrancarlo oculto en la bandeja al iniciar sesión: panel-portatil --tray &"
