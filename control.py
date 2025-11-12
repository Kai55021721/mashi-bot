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
    update    - Actualiza el código desde Git y reinicia el bot
    status    - Muestra el estado del servicio
    logs      - Muestra los logs del servicio
"""

import sys
import subprocess
import os

# Configuración SSH (ajusta según tu setup)
SSH_USER = "javierhorta2024"
SSH_HOST = "34.172.219.194"  # IP de la instancia (instance-20251004-005005)
REMOTE_DIR = "mashi-bot"
SERVICE_NAME = "telegram-bot.service"

def run_ssh_command(command):
    """Ejecuta un comando SSH en el servidor remoto."""
    ssh_command = f"ssh -t {SSH_USER}@{SSH_HOST} \"{command}\""
    try:
        result = subprocess.run(ssh_command, shell=True, capture_output=True, text=True)
        print(result.stdout)
        if result.stderr:
            print("Errores:", result.stderr)
        return result.returncode == 0
    except Exception as e:
        print(f"Error ejecutando comando SSH: {e}")
        return False

def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)

    action = sys.argv[1].lower()

    if action == "start":
        print("Iniciando el servicio del bot...")
        run_ssh_command(f"sudo systemctl start {SERVICE_NAME}")

    elif action == "stop":
        print("Deteniendo el servicio del bot...")
        run_ssh_command(f"sudo systemctl stop {SERVICE_NAME}")

    elif action == "restart":
        print("Reiniciando el servicio del bot...")
        run_ssh_command(f"sudo systemctl restart {SERVICE_NAME}")

    elif action == "update":
        print("Actualizando código y reiniciando el bot...")
        commands = [
            f"cd {REMOTE_DIR}",
            "git pull",
            f"sudo systemctl restart {SERVICE_NAME}",
            f"sudo systemctl status {SERVICE_NAME}"
        ]
        run_ssh_command(" && ".join(commands))

    elif action == "status":
        print("Verificando estado del servicio...")
        run_ssh_command(f"sudo systemctl status {SERVICE_NAME}")

    elif action == "logs":
        print("Mostrando logs del servicio...")
        run_ssh_command(f"sudo journalctl -u {SERVICE_NAME} -n 20 --no-pager")

    else:
        print(f"Acción '{action}' no reconocida.")
        print("Acciones disponibles: start, stop, restart, update, status, logs")
        sys.exit(1)

if __name__ == "__main__":
    main()