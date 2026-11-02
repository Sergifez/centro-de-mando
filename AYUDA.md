# Centro de mando

Un solo panel para configurar y vigilar el portátil: energía, pantalla, audio, red, escritorio, aplicaciones, disco y más. Se abre con **F1** en cualquier momento desde esta ayuda.

## Primeros pasos

- **Barra lateral:** las páginas están agrupadas (General, Hardware, Conectividad, Personalización, Sistema).
- **Tarjetas:** cada ajuste es una tarjeta con su interruptor, lista o deslizador. Pasa el ratón por encima para ver más detalle.
- **Buscador (Ctrl+K):** escribe para filtrar los ajustes de todas las páginas a la vez.
- **Consola inferior:** muestra con hora todo lo que hace el panel (▶ empieza, ✓ terminó bien, ✗ error).

## Aplicar y descartar cambios

El panel trabaja en **modo acumulado**: al cambiar un ajuste, su tarjeta se marca con un borde amarillo, pero todavía no pasa nada.

- **Aplicar cambios** ejecuta todos los marcados de una vez.
- **Descartar** los anula sin tocar el sistema.
- Los ajustes con candado (borde naranja) necesitan permisos de administrador. Se piden **una sola vez** para todo el lote.
- Si cierras con cambios pendientes, el panel pregunta antes de descartarlos.

## Resumen

Panel de estado en vivo, con refresco cada segundo:

- Cuatro **medidores**: CPU, memoria, temperatura y batería. Cambian de verde a amarillo y rojo según el nivel.
- Tres **gráficas** de los últimos 90 segundos: CPU y memoria, temperatura, y red (bajada y subida).
- Barra de **disco**, datos sueltos (gobernador, brillo, carga, tiempo encendido) y **alertas** si algo requiere atención.

## Presets

Perfiles que cambian varios ajustes a la vez: **Ahorro**, **Equilibrado** y **Rendimiento**. Antes de aplicar se muestra una vista previa de lo que cambiará, y **Revertir último preset** devuelve todo a como estaba.

## Hardware

- **Energía:** TLP, gobernador de CPU con batería y con corriente, turbo, suspensión de USB, ahorro Wi-Fi, acción al cerrar la tapa y apagado de pantalla.
- **Pantalla:** brillo, compositor, temperatura de color y resolución.
- **Audio:** volumen, silenciar salida o micrófono, y accesos al mezclador.
- **Entrada:** touchpad (tocar para clic, desplazamiento natural, velocidad) y distribución de teclado.
- **Batería:** salud real de la celda (capacidad actual frente a la de fábrica), consumo, voltaje y autonomía estimada. También muestra el modelo, la **referencia de recambio** (p. ej. `L15S4A01`), el fabricante y el portátil, con una nota sobre qué buscar para comprar una igual.

## Conectividad

- **Red:** Wi-Fi, Bluetooth y editor de conexiones.
- **Nube (Drive):** monta Google Drive con rclone, opcionalmente al iniciar sesión, y permite abrir la carpeta o ver el registro.

## Personalización

- **Escritorio, Ventanas, Compositor:** tema de Openbox, botones de la barra de título, número de escritorios, sombras, fundidos y opacidades.
- **Conky y Barras tint2:** activar, posicionar y ajustar las barras y los monitores del escritorio.
- **Arranque:** qué programas se lanzan al iniciar sesión. Interruptores sencillos, sin editar el archivo a mano.
- **Atajos:** lista de los atajos de Openbox. Puedes **añadir**, **cambiar la tecla** (se captura pulsando la combinación) y **eliminar**. Cada cambio guarda una copia de seguridad y recarga Openbox.

- **Archivos:** abre en tu editor de texto los archivos de configuración de tint2, conky, picom, Openbox, rofi, GTK, terminator y `.bashrc`. Elige el editor (Automático usa el primero que haya instalado) y, tras guardar, pulsa **Recargar** en el grupo para que la herramienta lea los cambios. Los archivos que son enlaces a `~/dotfiles` se marcan, y ahí git guarda el historial.

Antes de tocar `rc.xml`, `autostart`, `picom.conf`, tint2 o conky el panel guarda una copia en `~/.config/panel-portatil/backups/`.

## Sistema

- **Servicios:** arrancar y parar servicios habituales (Apache, PostgreSQL, Ollama, SSH…).
- **Sistema:** swappiness, TRIM semanal y tareas programadas.
- **Actualizaciones:** paquetes de apt pendientes, con botón para actualizar en una terminal.
- **Procesos:** los que más CPU o memoria usan, con opción de cerrarlos.
- **Dotfiles:** ver el estado de `~/dotfiles`, hacer commit de los archivos que marques y subirlos (con confirmación).

### Disco

- Espacio de cada partición.
- **Limpieza:** caché de apt y registros del sistema (piden contraseña).
- **Caché de usuario:** lista de cada programa de `~/.cache` de mayor a menor, con botón **Borrar** por programa. Pide confirmación y solo borra esa carpeta.

## Apps (AppImage)

Todas tus AppImage viven en `~/Applications` y se gestionan desde aquí.

- **Ejecutar**, **Eliminar** (van a la papelera, junto con su entrada de menú) y **Comprobar / Actualizar**.
- **Actualizar:** usa la información de actualización que lleva cada AppImage. Descarga la nueva versión aparte, comprueba que sea válida y solo entonces sustituye a la anterior, que queda en la **papelera** por si hace falta volver atrás.
- Si una app no tiene información de actualización (o su dirección ya no existe), se indica en su tarjeta y hay que bajarla a mano con **Añadir…**.
- **Traer las dispersas…** mueve a `~/Applications` las AppImage que estén en otras carpetas (no toca puntos de montaje como la nube).
- **Añadir al menú…** crea la entrada en el menú de aplicaciones leyendo el nombre y el icono del propio AppImage. Eliges el nombre y la **sección** (Oficina, Desarrollo, Gráficos, Internet, Juegos, Sistema, Multimedia, Utilidades, Ajustes o Ciencia). Después el botón pasa a **Menú…** para cambiarla o quitarla.

## Bandeja y avisos

Al cerrar la ventana con la **X**, el panel no se cierra: queda en la bandeja del sistema.

- **Clic** en el icono: muestra u oculta la ventana. **Clic derecho:** menú con *Abrir*, *Ir al Resumen*, *Avisos de escritorio*, *Probar un aviso* y *Salir*.
- Para cerrarlo de verdad usa **Salir** en ese menú.
- Para que arranque oculto al iniciar sesión, añade `panel-portatil --tray &` al autostart.

**Avisos de escritorio** (se pueden desactivar en el menú de la bandeja). Cada uno salta una vez y vuelve a estar listo cuando la situación se normaliza:

| Aviso | Cuándo |
|---|---|
| Batería baja | 20 % o menos, descargando |
| Batería crítica | 10 % o menos, descargando |
| CPU muy caliente | 85 °C o más |
| Disco casi lleno | La raíz al 90 % o más |
| Aplicaciones con novedades | AppImage con versión nueva (se comprueba cada 12 h) |

## Atajos de teclado

| Tecla | Acción |
|---|---|
| F1 | Abrir esta ayuda |
| Ctrl+K | Buscar ajustes |

## Solución de problemas

- **Un ajuste aparece desactivado o no hace nada:** falta el programa que lo gestiona (por ejemplo `tlp`, `brightnessctl` o `rclone`). Instálalo y reabre el panel.
- **Los cambios que piden contraseña fallan:** necesita un agente de autorización de PolicyKit en marcha (p. ej. `lxpolkit`).
- **No veo los cambios de código tras actualizar el panel:** al cerrar con la X se queda en la bandeja y al abrirlo de nuevo se reutiliza esa instancia. Ciérralo con *Salir* y ábrelo otra vez.
- **Un cambio salió mal:** las copias de seguridad están en `~/.config/panel-portatil/backups/`.
- **No llegan avisos:** comprueba que el panel esté en la bandeja, que *Avisos de escritorio* esté marcado y que haya un servidor de notificaciones activo.
