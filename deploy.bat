@echo off
echo ==================================================
echo  DESPLEGANDO BOT MASHI EN EL SERVIDOR...
echo ==================================================

ssh -t javierhorta2024@instance-20251004-005005@34.172.219.194 "cd mashi-bot && git pull && sudo systemctl restart telegram-bot.service && echo '--- Proceso finalizado. Verificando estado: ---' && sudo systemctl status telegram-bot.service"

echo.
echo ==================================================
echo  Script de despliegue finalizado.
echo ==================================================
pause
