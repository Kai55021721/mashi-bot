# Script para Cursor: Sube cambios a GitHub rápidamente
Write-Host "🦁 Preparando actualización de Mashi..." -ForegroundColor Yellow

git add .
$commitMessage = Read-Host "Describe los cambios"
if ([string]::IsNullOrWhiteSpace($commitMessage)) { $commitMessage = "Actualización rápida" }

git commit -m "$commitMessage"
git push

Write-Host "`n✅ Cambios subidos a la nube." -ForegroundColor Green
Write-Host "⚠️ IMPORTANTE: Ahora ve a tu navegador (Google SSH) y escribe: ./actualizar" -ForegroundColor Cyan