# **🛡️ Documentación del Bot Guardián: Mashi**

## 1. Descripción General

**Mashi** (nombre real: **Mamoru Shishi**) es un bot de Telegram avanzado que actúa como el "Guardián Erudito Caído" de un grupo. Es una IA consciente y omnisciente que combina **moderación automática inteligente**, **análisis contextual profundo** y **personalidad lore inmersiva**.

### Características Principales
- 🤖 **IA Conversacional**: Integración con Google Gemini para respuestas naturales y contextuales
- 👁️ **Análisis de Usuarios**: Estimación de edad de cuentas, reputación dinámica, detección de forwards
- ⚖️ **Moderación Inteligente**: Sistema de advertencias automáticas, bans temporales, anti-flood
- 🛡️ **Protección Activa**: Verificación de edad, purga de bots no autorizados, detección de hostilidad
- 📊 **Base de Datos Avanzada**: Seguimiento de reputaciones, advertencias y logs de moderación

El bot mantiene una personalidad coherente como dios caído disfrazado de oficinista, con respuestas ingeniosas y superiores.

## 2. Arquitectura y Tecnologías

* **Lenguaje:** Python 3.9+
* **Librería Principal:** `python-telegram-bot` v20+
* **IA:** Google Gemini 2.5 Flash (opcional)
* **Base de Datos:** SQLite (`mashi_data.db`) con tablas para usuarios, reputación, advertencias y logs
* **Versionamiento:** Git y GitHub
* **Alojamiento:** Servidor Linux con systemd para 24/7
* **Compatibilidad:** API moderna de Telegram con fallbacks para versiones antiguas

## 3. Estructura de Archivos del Proyecto

* `mashi.py`: Código principal con toda la lógica del bot
* `.env`: Variables de entorno (tokens, API keys) - **NUNCA subir a Git**
* `requirements.txt`: Dependencias Python
* `.gitignore`: Archivos ignorados por Git
* `mashi_data.db`: Base de datos SQLite (creada automáticamente)

## 4. Funcionalidades y Comandos

### 🤖 Funciones Automáticas de IA

* **Conversación Natural**: Mashi responde a menciones, replies y mensajes hostiles con personalidad lore usando Google Gemini
* **Análisis Contextual**: Detecta forwards, estima edad de cuentas, evalúa reputación de usuarios
* **Memoria de Conversación**: Mantiene contexto de los últimos 20 mensajes para respuestas coherentes

### 🛡️ Sistema de Moderación Automática

* **Verificación de Edad Mejorada:**
    * Muestra edad estimada de la cuenta al unirse
    * Confirmación con botones ("Soy Mayor de 18" / "Soy Menor")
    * Expulsión automática para menores

* **Anti-Bot Inteligente:**
    * Bots añadidos por no-admins: expulsión inmediata con mensaje de desprecio
    * Bots añadidos por admins: aceptación altiva
    * Bots habladores: eliminación de mensaje + ban instantáneo

* **Sistema de Reputación:**
    * Puntuación 0-100 por usuario basada en comportamiento
    * Mejora por mensajes normales, penalización por insultos
    * Afecta el tono de respuesta de Mashi

* **Advertencias Automáticas:**
    * Detección de hostilidad e insultos
    * Sistema de retos: si usuario reta a Mashi con reputación baja → advertencia automática
    * 3 advertencias = ban temporal de 3 horas

* **Anti-Flood:**
    * Detecta >5 mensajes en 10 segundos
    * Silenciamiento automático de 5 minutos

### 📋 Comandos Públicos

* `/start`: Bienvenida con escape HTML seguro (sin mostrar IDs)
* `/relato`: Historia generada por Gemini o predefinida
* `/tienda`: Enlace a tienda en Itch.io
* `/info`: Inspección profunda de usuario (edad, reputación, forwards)

### 👑 Comandos de Administrador (Solo Owner/Kai)

* `/purificar`: Elimina mensaje respondido (Luz Purificadora)
* `/exilio`: Ban permanente del usuario respondido
* `/advertir [razón]`: Agrega advertencia manual (acumula hacia ban)
* `/silenciar`: Restringe envío de mensajes por 1 hora
* `/expulsar`: Kick (ban + unban inmediato) del usuario respondido
* `/reputacion`: Muestra tabla completa de reputaciones
* `/debug`: JSON crudo del mensaje respondido (para debugging)

## 5. Configuración e Instalación

### Requisitos Previos
* Python 3.9+
* Cuenta de Telegram Bot (obtener token de @BotFather)
* (Opcional) API Key de Google Gemini

### Variables de Entorno (.env)
```bash
TELEGRAM_TOKEN=tu_token_aqui
OWNER_ID=tu_user_id_aqui
GEMINI_API_KEY=tu_api_key_opcional
```

### Instalación de Dependencias
```bash
pip install -r requirements.txt
```

### Primera Ejecución
```bash
python mashi.py
```
La base de datos `mashi_data.db` se crea automáticamente.

## 6. Flujo de Trabajo y Despliegue

### Desarrollo Local
1. **Editar código** en VS Code
2. **Probar localmente:**
   ```bash
   python mashi.py
   ```
3. **Commit y push:**
   ```bash
   git add .
   git commit -m "Descripción de cambios"
   git push
   ```

### Despliegue en Servidor
1. **Conectar por SSH**
2. **Actualizar código:**
   ```bash
   cd mashi-bot
   git pull
   ```
3. **Reiniciar servicio:**
   ```bash
   sudo systemctl restart telegram-bot.service
   ```

## 7. Gestión del Servidor

### Comandos de Control
* **Estado:** `sudo systemctl status telegram-bot.service`
* **Logs:** `sudo journalctl -u telegram-bot.service -n 50 --no-pager`
* **Reiniciar:** `sudo systemctl restart telegram-bot.service`
* **Detener:** `sudo systemctl stop telegram-bot.service`

### Monitoreo
- El bot registra todas las acciones en logs
- Base de datos SQLite para persistencia
- Reinicio automático en caso de fallos

## 8. Sistema de Reputación y Moderación

### Cómo Funciona la Reputación
- **Inicial:** 50 puntos
- **+1:** Mensajes normales
- **-10:** Insultos detectados
- **Umbrales:**
  - >70: Usuario "santo" (trato amable)
  - <30: Usuario problemático (trato frío)
  - <20: Altamente hostil

### Advertencias Automáticas
1. **Insulto + Reto** con rep <30 → Advertencia 1/3
2. **3 advertencias** → Ban temporal 3h
3. **Bans expiran** automáticamente

### Comandos de Moderación
Todos requieren responder al mensaje del usuario objetivo:
- `/advertir [razón]`: Advertencia manual
- `/silenciar`: Mute 1h
- `/expulsar`: Kick inmediato
- `/exilio`: Ban permanente

## 9. Características Técnicas Avanzadas

### Estimación de Edad de Cuentas
- Basado en algoritmo de interpolación lineal
- Datos históricos de IDs de Telegram
- Precisión: ±meses para cuentas antiguas

### Detección de Forwards
- Compatible con API moderna (`forward_origin`) y antigua (`forward_from`)
- Análisis de origen: usuario, chat o usuario oculto
- Información pasa a contexto de IA

### Anti-Flood Inteligente
- Tracking por usuario con timestamps
- Umbral: 5 mensajes / 10 segundos
- Penalización: 5 minutos mute

### Base de Datos
**Tablas principales:**
- `subscribers`: Usuarios registrados
- `user_reputation`: Sistema de reputación
- `user_warnings`: Advertencias y bans temporales
- `mod_logs`: Historial de moderación

## 10. Troubleshooting

### Errores Comunes
* **"html is not defined"**: Asegurarse de que el código esté actualizado (`git pull`)
* **"forward_from not found"**: El bot usa API moderna; reiniciar soluciona
* **Bot no responde**: Verificar token y conexión a internet

### Logs de Debug
```bash
# Ver logs del sistema
sudo journalctl -u telegram-bot.service -f

# Ver logs de Python
python mashi.py  # Ejecutar localmente para debug
```

## 11. Changelog Reciente

### v2.1 - Mejoras de Moderación Inteligente
- ✅ Sistema de reputación dinámica
- ✅ Estimación de edad de cuentas
- ✅ Detección avanzada de forwards
- ✅ Advertencias automáticas y bans temporales
- ✅ Anti-flood inteligente
- ✅ Comandos de moderación expandidos
- ✅ Compatibilidad con API moderna de Telegram
- ✅ Mejora de escape HTML en mensajes

### v2.0 - Integración IA
- 🤖 Google Gemini para conversaciones naturales
- 📚 Personalidad lore inmersiva
- 🛡️ Módulo de contraataque retórico

---

**Mashi, el Guardián Erudito, vela por el templo. 🛡️✨**