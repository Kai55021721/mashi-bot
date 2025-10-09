# **Documentación del Bot Guardián: Mashi**

## 1. Descripción General

**Mashi** (nombre real: **Mamoru Shishi**) es un bot de Telegram diseñado para actuar como el "Guardián Erudito Caído" de un grupo. Su propósito principal es la **administración y protección del chat**, manteniendo una personalidad coherente, sabia y superior.

Además de sus funciones de moderación en Telegram, el bot ejecuta un **servidor web ligero** que muestra una página de estado para confirmar que el proceso está activo.

## 2. Arquitectura y Tecnologías

*   **Lenguaje:** Python 3
*   **Librerías Principales:**
    *   `python-telegram-bot`: Para la interacción con la API de Telegram.
    *   `Flask`: Para el servidor web de monitoreo.
    *   `requests`: Para realizar peticiones HTTP (usado en nuevas funciones).
    *   `Pillow`: Para manipulación de imágenes.
*   **Base de Datos:** SQLite para el registro de usuarios (`mashi_data_v2.db`).
*   **Versionamiento:** Git y GitHub.
*   **Alojamiento (Hosting):** Servidor Virtual (VM) en Google Cloud Platform (instancia `e2-micro`).
*   **Gestor de Servicio:** `systemd` en Linux (Debian) para asegurar que el bot se ejecute 24/7.

## 3. Estructura de Archivos del Proyecto

*   `mashi.py`: El corazón del bot. Contiene la lógica del bot de Telegram y del servidor web Flask, que se ejecutan en hilos separados.
*   `.env`: Archivo de configuración que almacena de forma segura el `TELEGRAM_TOKEN`. **Nunca debe subirse a GitHub.**
*   `requirements.txt`: Lista las dependencias de Python (`python-telegram-bot`, `Flask`, `requests`, `Pillow`).
*   `.gitignore`: Especifica qué archivos (como `.env` y la base de datos) deben ser ignorados por Git.
*   `mashi_data_v2.db`: Archivo de la base de datos SQLite. Almacena información de los usuarios.
*   `index.html`: Página web básica que actúa como indicador de estado del bot.
*   `subscribestar_banner.png`: Imagen de base para la función de banner.
*   `banner_id.txt`: Almacena el ID del mensaje del banner en Telegram para poder editarlo.

## 4. Funcionalidades y Comandos

### Funcionalidad Web

*   **Página de Estado:** Al acceder a la IP del servidor, se muestra `index.html`, confirmando que el proceso del bot está activo.

### Comandos Públicos de Telegram

*   `/start`: Inicia la interacción con el bot. Mashi se presenta con su mensaje de bienvenida.
*   `/relato`: Mashi cuenta una breve historia o reflexión sobre su pasado.
*   `/chiste`: Mashi comparte una anécdota con su humor seco y arcaico.
*   `/cicatriz`: Mashi muestra una de sus "cicatrices", una reflexión sobre su deber.

### Comandos de Administrador (Solo "Maestro Kai")

*   `/purificar`: (Habilidad: "Luz Purificadora") Se usa **respondiendo a un mensaje** que se desea borrar. Mashi elimina el mensaje original y el comando.
*   `/actualizar_banner`: Actualiza y edita un mensaje de banner predefinido en el canal, posiblemente usando `requests` para obtener datos y `Pillow` para modificar la imagen `subscribestar_banner.png`.

## 5. Flujo de Trabajo: Cómo Editar y Actualizar el Bot

El flujo de trabajo general se mantiene, pero el script ahora es más complejo.

### **Paso A: Detener el Bot en el Servidor (Opcional pero recomendado)**

1.  Conéctate al servidor por **SSH**.
2.  Ejecuta: `sudo systemctl stop telegram-bot.service`

### **Paso B: Editar el Código en tu PC**

1.  Abre el proyecto en **Visual Studio Code**.
2.  Realiza los cambios en `mashi.py`, `index.html` u otros archivos.

### **Paso C: Probar los Cambios en Local**

1.  Asegúrate de que el bot en el servidor esté detenido.
2.  En la terminal de VS Code, activa el entorno virtual: `& C:/Users/Kai/Documents/mashi_bot/.venv/Scripts/Activate.ps1`
3.  Ejecuta el bot en tu PC: `python mashi.py`
4.  Abre Telegram y prueba los comandos. Abre un navegador y visita `http://127.0.0.1:5000` (o el puerto que hayas configurado) para probar la página de estado.
5.  Detén el script con `Ctrl + C`.

### **Paso D: Guardar los Cambios en GitHub**

1.  Prepara los archivos: `git add .`
2.  Guarda los cambios: `git commit -m "Tu mensaje descriptivo"`
3.  Sube los cambios: `git push`

### **Paso E: Actualizar el Código en el Servidor**

1.  Conéctate al servidor por **SSH**.
2.  Navega a la carpeta del bot: `cd mashi-bot`
3.  Descarga la última versión: `git pull`
4.  (Opcional) Si añadiste nuevas librerías, actualiza las dependencias: `pip install -r requirements.txt`

### **Paso F: Reiniciar el Bot en el Servidor**

1.  Reinicia el servicio para aplicar los cambios:
    `sudo systemctl restart telegram-bot.service`
2.  Verifica que todo funcione correctamente (el servicio debe estar `active (running)`):
    `sudo systemctl status telegram-bot.service`

## 6. Gestión del Servidor (Cheatsheet de Comandos)

Los comandos de `systemd` para gestionar el servicio no cambian:

*   **Detener:** `sudo systemctl stop telegram-bot.service`
*   **Iniciar:** `sudo systemctl start telegram-bot.service`
*   **Reiniciar:** `sudo systemctl restart telegram-bot.service`
*   **Ver estado y logs:** `sudo systemctl status telegram-bot.service` (presiona `Q` para salir).