@echo off
setlocal

echo.
echo  ================================
echo   Print Tracker - Iniciar agente
echo  ================================
echo.

net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] Ejecutar como Administrador.
    echo Clic derecho en iniciar.bat ^> "Ejecutar como administrador"
    pause
    exit /b 1
)

set /p CLAVE="Ingrese la clave de administrador: "
if not "%CLAVE%"=="admin1234" (
    echo [ERROR] Clave incorrecta.
    pause
    exit /b 1
)

nssm start PrintTrackerAgent >nul 2>&1
echo.
echo  [OK] Agente iniciado.
echo.
pause
