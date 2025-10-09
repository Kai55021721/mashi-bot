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

## 5. Flujo de Trabajo y Despliegue

El proceso de edición, versionamiento y despliegue se ha simplificado.

### **Paso 1: Editar el Código en tu PC**

1.  Abre el proyecto en **Visual Studio Code**.
2.  Realiza los cambios necesarios en los archivos del proyecto.

### **Paso 2: Probar los Cambios en Local (Recomendado)**

1.  En una terminal, activa el entorno virtual: `& .\.venv\Scripts\Activate.ps1`
2.  Ejecuta el bot en tu PC: `python mashi.py`
3.  Prueba las nuevas funcionalidades en Telegram y en el navegador (`http://127.0.0.1:5000`).
4.  Detén el script con `Ctrl + C`.

### **Paso 3: Guardar y Subir los Cambios a GitHub**

1.  Prepara los archivos: `git add .`
2.  Guarda los cambios con un mensaje claro: `git commit -m "Tu mensaje descriptivo"`
3.  Sube los cambios al repositorio remoto: `git push`

### **Paso 4: Desplegar en el Servidor (Automático)**

1.  Ejecuta el script de despliegue:
    `deploy.bat`
2.  El script se encargará de conectarse al servidor, descargar los últimos cambios (`git pull`) y reiniciar el servicio del bot (`systemd`). Al finalizar, mostrará el estado del servicio para confirmar que todo está funcionando.

## 6. Entorno de Desarrollo

### Extensiones Recomendadas

Para una mejor experiencia de desarrollo en Visual Studio Code, se recomienda instalar la siguiente extensión:

*   **Gemini Code Assist (`google.geminicodeassist`)**: Asistente de código basado en IA para autocompletado, generación de código y más. La recomendación se encuentra en el archivo `.vscode/extensions.json`.

## 7. Gestión del Servidor (Cheatsheet de Comandos)

Los comandos de `systemd` para gestionar el servicio no cambian:

*   **Detener:** `sudo systemctl stop telegram-bot.service`
*   **Iniciar:** `sudo systemctl start telegram-bot.service`
*   **Reiniciar:** `sudo systemctl restart telegram-bot.service`
*   **Ver estado y logs:** `sudo systemctl status telegram-bot.service` (presiona `Q` para salir).