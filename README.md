# Centro de mando

Panel de control de un solo sitio para el portátil (Lenovo ideapad 100, Debian 13, Openbox).
PyQt6, tema oscuro con panel lateral por categorías, inspirado en Asere.

Lanzar: `panel-portatil` (`~/.local/bin/panel-portatil`) o desde el menú de Openbox.
Reaplicar ajustes de sesión al arrancar (touchpad, teclado, DPMS, temperatura de color):
`panel-portatil --apply &` en el autostart de Openbox.

## Cómo funciona

- **Modo acumulado:** los cambios se marcan (borde amarillo) y se aplican juntos con
  *Aplicar cambios*. Los que necesitan root (candado / borde naranja) van en **una sola**
  autorización `pkexec`. *Descartar* los anula; al cerrar con cambios pendientes pregunta.
- **Buscador** (`Ctrl+K`): filtra los ajustes de todas las categorías.
- **Consola** inferior: registro con hora de cada acción (`▶` inicio, `✓` ok, `✗` error).
- **Copias de seguridad:** antes de editar `autostart`, `rc.xml`, `picom.conf`, `.tint2rc` o
  `.conkyrc` se copia el original en `~/.config/panel-portatil/backups/`.
- **Recargas agrupadas:** varios cambios en tint2/picom/Openbox/conky = una sola recarga.

## Categorías

| Grupo | Páginas |
|---|---|
| General | Resumen (con alertas), Presets (Ahorro / Equilibrado / Rendimiento con vista previa y reversión) |
| Hardware | Energía (TLP, tapa, DPMS), Pantalla, Audio, Entrada (touchpad, teclado), Batería (salud) |
| Conectividad | Red, Nube (Drive con rclone) |
| Personalización | Escritorio, Conky, Barras tint2, Compositor (picom), Ventanas (Openbox), Arranque, Atajos (editables) |
| Sistema | Servicios, Sistema, Actualizaciones, Disco (limpieza), Procesos, Apps (AppImage), Dotfiles (commit/push) |

## Archivos

| Archivo | Contenido |
|---|---|
| `panel.py` | Interfaz: ventana, barra lateral, tarjetas, modo acumulado, presets, resumen |
| `settings.py` | Clase `S` (un ajuste) y todas las categorías en `build()` / `CATEGORIES` |
| `deskcfg.py` | Edición segura de autostart, picom, rc.xml, tint2 y conky |
| `pages.py` | Páginas de información: Batería, Procesos, Atajos, Disco, Actualizaciones |
| `root_helper.py` | Operaciones con root, **solo de una lista blanca**, vía `pkexec` |
| `panel-portatil.svg` | Icono |

## Añadir cosas

- **Un ajuste:** un `S(id, categoría, título, descripción, tipo, get=…, set=…)` en `settings.py`.
  Tipos: `toggle`, `choice`, `slider`, `button`. Con `root=lambda v: [[op, …]]` se ejecuta como root.
- **Una categoría:** una tupla en `CATEGORIES`.
- **Una página de información:** clase en `pages.py` registrada en `PAGES` (misma clave que la categoría).
- **Una operación root:** función `op_*` en `root_helper.py` y entrada en `OPS`, validando los argumentos.

## Notas

- `root_helper.py` es un archivo del usuario que se ejecuta como root: quien pueda editarlo escala
  privilegios. Para endurecerlo, instalarlo en `/usr/local/lib` con dueño root y una política polkit.
- Los widgets de tarjeta deben tener padre antes de mostrarse (si no, parpadean como ventanas sueltas).
- Estado de sesión en `~/.config/panel-portatil/state.json`; instantánea del último preset en
  `preset-snapshot.json`.

## Resumen gráfico, atajos, dotfiles y bandeja

- **Resumen:** cuatro medidores (CPU, memoria, temperatura, batería) y tres gráficas con histórico
  de 90 s (CPU+RAM, temperatura, red ↓↑), barra de disco y alertas. Widgets en `dash.py`.
- **Atajos:** añadir, cambiar tecla (se captura pulsándola) y eliminar; edita `rc.xml` con
  copia de seguridad y `openbox --reconfigure`. La chuleta de conky es un archivo aparte.
- **Dotfiles:** lista los cambios de `~/dotfiles`, commit solo de lo marcado y push con confirmación.
- **Bandeja:** icono con tooltip (batería, CPU); clic alterna la ventana; la X solo oculta, *Salir* del
  menú cierra. Instancia única; `panel-portatil --tray` arranca oculto.
- **Apps (AppImage):** todas viven en `~/Applications` (`apps.py`). Ejecutar, Comprobar/Actualizar y Eliminar
  (a la papelera, con su lanzador de menú). La actualización lee la sección ELF `.upd_info` de cada AppImage
  (`gh-releases-zsync` vía API de GitHub, o `zsync|URL` comparando `Length`); descarga a `.nombre.part`, comprueba
  que sea ELF y solo entonces sustituye (la versión vieja va a la papelera y se reescriben los `.desktop`).
  «Traer las dispersas…» mueve los AppImage de otras carpetas (ignora puntos de montaje como ~/Drive).
- **Menú de las AppImage:** el botón «Añadir al menú…» lee el `.desktop` y el icono del propio AppImage
  (`--appimage-extract`, sin ejecutarlo), deja elegir nombre y **sección** (Oficina, Desarrollo, Gráficos, Internet,
  Juegos, Sistema, Multimedia, Utilidades, Ajustes, Ciencia) y crea `~/.local/share/applications/appimage-*.desktop`
  con una única categoría. Con entrada ya creada, el botón pasa a «Menú…» para cambiarla o quitarla.
  Para que el menú de Openbox las muestre, `obamenu` (dotfiles) lee también `~/.local/share/applications`.
