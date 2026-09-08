# Script para iniciar el servidor de Cyclops Fichas
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "   Iniciando servidor Cyclops Fichas...  " -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

# Aseguramos que estamos en el directorio correcto
Set-Location -Path "C:\Proyectos\cyclops-fichas"

# Instalamos los requerimientos básicos (FastAPI, Uvicorn, Jinja2, etc.)
Write-Host "
[1/2] Verificando dependencias..." -ForegroundColor Yellow
pip install -r requirements.txt

# Levantamos el servidor web con recarga automática
Write-Host "
[2/2] Levantando el servidor local..." -ForegroundColor Yellow
Write-Host "La aplicación estará disponible en: http://127.0.0.1:8000" -ForegroundColor Green
Write-Host "Presiona CTRL+C en esta consola para apagar el servidor." -ForegroundColor DarkGray
Write-Host ""
uvicorn app.main:app --reload
