Aquí tienes el `README.md` actualizado para reflejar la nueva lógica anti-bots que acabamos de implementar.

He modificado la sección "Funciones Automáticas" para incluir la nueva lógica de "Purga Reactiva" y la excepción para bots añadidos por administradores.

---

# **Documentación del Bot Guardián: Mashi**

## 1. Descripción General

**Mashi** (nombre real: **Mamoru Shishi**) es un bot de Telegram diseñado para actuar como el "Guardián Erudito Caído" de un grupo. Su propósito principal es la **administración, protección y moderación activa del chat**, manteniendo una personalidad coherente, sabia y superior.

El bot gestiona un sistema de **verificación de edad** para nuevos miembros humanos y aplica una política **extremadamente agresiva contra bots no autorizados**, expulsándolos al unirse o al intentar hablar.

## 2. Arquitectura y Tecnologías

* **Lenguaje:** Python 3
* **Librería Principal:** `python-telegram-bot`
* **Base de Datos:** SQLite (`mashi_data.db`) para registrar usuarios y logs de moderación.
* **API Externa:** Google Gemini (opcional, para el comando `/relato` si la API key está presente).
* **Versionamiento:** Git y GitHub.
* **Alojamiento (Hosting):** Servidor Virtual (VM) en Google Cloud Platform (instancia `e2-micro`).
* **Gestor de Servicio:** `systemd` en Linux (Debian) para asegurar que el bot se ejecute 24/7.

## 3. Estructura de Archivos del Proyecto

* `mashi.py`: El corazón del bot. Contiene toda la lógica, comandos y respuestas.
* `.env`: Archivo de configuración que almacena de forma segura el `TELEGRAM_TOKEN`, `OWNER_ID` y `GEMINI_API_KEY`. **Nunca debe subirse a GitHub.**
* `requirements.txt`: Lista las dependencias de Python necesarias.
* `.gitignore`: Especifica qué archivos (como `.env` y la base de datos) deben ser ignorados por Git.
* `mashi_data.db`: Archivo de la base de datos SQLite.

## 4. Funcionalidades y Comandos

### Funciones Automáticas

* **Verificación de Edad:**
    * Cuando un nuevo miembro humano se une, el bot le da la bienvenida y le pide confirmar su edad con botones ("Soy Mayor de 18" / "Soy Menor").
    * Si el usuario confirma ser **mayor**, el mensaje se actualiza y se le permite quedarse.
    * Si el usuario confirma ser **menor**, es expulsado (baneado) automáticamente del grupo.

* **Gestión Anti-Bot (Al Unirse):**
    * **Si un bot es añadido por un mortal:** Mashi lo expulsa (banea) inmediatamente y publica un mensaje de desprecio.
    * **Si un bot es añadido por un Admin:** Mashi lo tolera, publicando un mensaje altivo donde acepta al "sirviente autómata" convocado por una autoridad.

* **Purga Reactiva (Anti-Bot Hablador):**
    * Mashi monitorea todos los mensajes del chat.
    * Si un bot (que no sea administrador) intenta enviar un mensaje, Mashi **borrará el mensaje y baneará al bot** instantáneamente por "atreverse a hablar sin permiso".

### Comandos Públicos

* `/start`: Inicia la interacción con el bot. Mashi se presenta con su mensaje de bienvenida actualizado.
* `/relato`: Mashi cuenta una breve historia o reflexión sobre su pasado (usa Gemini si está configurado, o una lista interna si no).
* `/tienda`: Muestra un botón que abre una Web App con la página de Itch.io especificada.

### Comandos de Administrador (Solo "Maestro Kai")

* `/purificar`
    * **Habilidad: "Luz Purificadora"**. Se usa **respondiendo a un mensaje** que se desea borrar. Mashi elimina el mensaje original y el comando.
* `/exilio`
    * Se usa **respondiendo a un usuario**. Mashi expulsa (banea) permanentemente a ese usuario del grupo.

## 5. Flujo de Trabajo y Despliegue

(El flujo de trabajo no ha cambiado)

### **Paso 1: Editar el Código en tu PC**
Abre el proyecto en **Visual Studio Code** y realiza tus cambios.

### **Paso 2: Probar los Cambios en Local (Recomendado)**
1.  Activa el entorno virtual: `& .\.venv\Scripts\Activate.ps1`
2.  Ejecuta el bot: `python mashi.py`
3.  Prueba las nuevas funciones en Telegram.
4.  Detén el script con `Ctrl + C`.

### **Paso 3: Guardar y Subir los Cambios a GitHub**
1.  Prepara los archivos: `git add .`
2.  Guarda los cambios: `git commit -m "Tu mensaje descriptivo"`
3.  Sube los cambios: `git push`

### **Paso 4: Desplegar en el Servidor**
1.  Conéctate al servidor por **SSH**.
2.  Navega a la carpeta del bot: `cd mashi-bot`
3.  Descarga los últimos cambios: `git pull`
4.  Reinicia el servicio del bot: `sudo systemctl restart telegram-bot.service`

## 6. Gestión del Servidor (Cheatsheet de Comandos)

### Control Remoto desde Consola Local

Ahora puedes controlar el bot directamente desde tu consola local usando el script `control.py`:

* **Detener el bot:** `python control.py stop`
* **Iniciar el bot:** `python control.py start`
* **Reiniciar el bot:** `python control.py restart`
* **Actualizar y reiniciar:** `python control.py update`
* **Ver estado:** `python control.py status`
* **Ver logs recientes:** `python control.py logs`

Este script usa SSH para conectarse automáticamente al servidor y ejecutar los comandos necesarios.

### Comandos Manuales (SSH Directo)

Si prefieres conectarte manualmente:

* **Detener:** `sudo systemctl stop telegram-bot.service`
* **Iniciar:** `sudo systemctl start telegram-bot.service`
* **Reiniciar:** `sudo systemctl restart telegram-bot.service`
* **Ver estado y logs:** `sudo systemctl status telegram-bot.service` (presiona `Q` para salir).