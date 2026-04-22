@echo off
setlocal

:: ============================================================
::  Print Tracker - Instalador del agente
::  Ejecutar como Administrador
:: ============================================================

echo.
echo  ================================
echo   Print Tracker - Instalador
echo  ================================
echo.

:: --- verificar que corre como administrador ---
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] Ejecutar como Administrador.
    echo Clic derecho en instalar.bat ^> "Ejecutar como administrador"
    pause
    exit /b 1
)

:: --- configuracion ---
set INSTALL_DIR=C:\PrintTracker
set SERVER_URL=http://TU_IP_SERVIDOR:8000

echo Directorio de instalacion: %INSTALL_DIR%
echo Servidor: %SERVER_URL%
echo.

:: --- crear carpeta ---
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

:: --- copiar agent.exe ---
if not exist "%~dp0agent.exe" (
    echo [ERROR] No se encontro agent.exe en la misma carpeta que este instalador.
    pause
    exit /b 1
)
copy /Y "%~dp0agent.exe" "%INSTALL_DIR%\agent.exe" >nul
echo [OK] agent.exe copiado

:: --- copiar nssm ---
if not exist "%~dp0nssm.exe" (
    echo [ERROR] No se encontro nssm.exe en la misma carpeta que este instalador.
    pause
    exit /b 1
)
copy /Y "%~dp0nssm.exe" "%SystemRoot%\System32\nssm.exe" >nul
echo [OK] nssm.exe instalado

:: --- desinstalar servicio previo si existe ---
sc query PrintTrackerAgent >nul 2>&1
if %errorLevel% equ 0 (
    echo Desinstalando version anterior...
    nssm stop PrintTrackerAgent >nul 2>&1
    nssm remove PrintTrackerAgent confirm >nul 2>&1
)

:: --- instalar servicio ---
nssm install PrintTrackerAgent "%INSTALL_DIR%\agent.exe"
nssm set PrintTrackerAgent AppEnvironmentExtra "SERVER_URL=%SERVER_URL%"
nssm set PrintTrackerAgent Start SERVICE_AUTO_START
nssm set PrintTrackerAgent AppRestartDelay 3000
nssm start PrintTrackerAgent

:: --- bloquear permisos: solo administradores pueden detener/eliminar el servicio ---
:: SY = Sistema, BA = Administradores → control total
:: IU = Usuarios comunes → solo pueden ver el estado, no detener ni eliminar
sc sdset PrintTrackerAgent "D:(A;;CCDCLCSWRPWPDTLOCRSDRCWDWO;;;SY)(A;;CCDCLCSWRPWPDTLOCRSDRCWDWO;;;BA)(A;;CCLCLORC;;;IU)" >nul
echo [OK] Permisos del servicio configurados

:: --- verificar ---
timeout /t 2 >nul
sc query PrintTrackerAgent | find "RUNNING" >nul
if %errorLevel% equ 0 (
    echo.
    echo  [OK] Agente instalado y corriendo correctamente.
    echo  Reportando a: %SERVER_URL%
) else (
    echo.
    echo  [ADVERTENCIA] El servicio fue instalado pero no esta corriendo.
    echo  Verificar en: Administrador de tareas ^> Servicios ^> PrintTrackerAgent
)

echo.
pause
