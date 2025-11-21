#!/usr/bin/env python3
"""
Control remoto para el bot Mashi.
Permite gestionar el bot desde la consola local sin necesidad de conectarse manualmente al servidor.

Uso:
    python control.py <acción>

Acciones disponibles:
    start     - Inicia el servicio del bot
    stop      - Detiene el servicio del bot
    restart   - Reinicia el servicio del bot
    update    - Descarga el código de GitHub y reinicia el bot (¡El más útil!)
    status    - Muestra el estado del servicio
    logs      - Muestra los últimos registros (logs)
"""

import sys
import subprocess

# --- CONFIGURACIÓN (Ajustada a tu entorno) ---
SSH_USER = "javierhorta2024"
SSH_HOST = "34.172.219.194"  # Tu IP Externa de Google Cloud
# Ruta exacta de tu llave privada (la que creamos sin contraseña)
SSH_KEY_PATH = r"C:\Users\javie\.ssh\google_key" 

REMOTE_DIR = "mashi-bot"
SERVICE_NAME = "telegram-bot.service"

def run_ssh_command(command):
    """Ejecuta un comando SSH en el servidor remoto usando tu llave."""
    # Se añade -i para usar la llave específica y -o StrictHostKeyChecking=no para evitar preguntas de "yes/no"
    ssh_command = f'ssh -i "{SSH_KEY_PATH}" -o StrictHostKeyChecking=no -t {SSH_USER}@{SSH_HOST} "{command}"'
    
    try:
        # Ejecutar el comando y mostrar la salida en tiempo real
        result = subprocess.run(ssh_command, shell=True)
        return result.returncode == 0
    except Exception as e:
        print(f"❌ Error ejecutando comando SSH: {e}")
        return False

def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)

    action = sys.argv[1].lower()

    if action == "start":
        print("🚀 Iniciando Mashi...")
        run_ssh_command(f"sudo systemctl start {SERVICE_NAME}")

    elif action == "stop":
        print("🛑 Deteniendo Mashi...")
        run_ssh_command(f"sudo systemctl stop {SERVICE_NAME}")

    elif action == "restart":
        print("🔄 Reiniciando servicio...")
        run_ssh_command(f"sudo systemctl restart {SERVICE_NAME}")

    elif action == "update":
        print("📥 Actualizando desde GitHub y reiniciando...")
        # Comandos encadenados: Ir a carpeta -> Git Pull -> Reiniciar -> Mostrar Estado
        commands = [
            f"cd {REMOTE_DIR}",
            "git pull",
            f"sudo systemctl restart {SERVICE_NAME}",
            f"sudo systemctl status {SERVICE_NAME} --no-pager"
        ]
        # Unimos los comandos con '&&' para que se ejecuten uno tras otro
        run_ssh_command(" && ".join(commands))

    elif action == "status":
        print("📊 Verificando estado...")
        run_ssh_command(f"sudo systemctl status {SERVICE_NAME} --no-pager")

    elif action == "logs":
        print("📝 Mostrando últimos 20 logs...")
        run_ssh_command(f"sudo journalctl -u {SERVICE_NAME} -n 20 --no-pager")

    else:
        print(f"⚠️ Acción '{action}' no reconocida.")
        print("Usa: start, stop, restart, update, status, logs")
        sys.exit(1)

if __name__ == "__main__":
    main()