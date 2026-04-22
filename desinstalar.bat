@echo off
setlocal

echo.
echo  ================================
echo   Print Tracker - Desinstalador
echo  ================================
echo.

:: --- verificar que corre como administrador ---
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] Ejecutar como Administrador.
    echo Clic derecho en desinstalar.bat ^> "Ejecutar como administrador"
    pause
    exit /b 1
)

:: --- pedir clave ---
set /p CLAVE="Ingrese la clave de administrador: "
if not "%CLAVE%"=="admin1234" (
    echo [ERROR] Clave incorrecta.
    pause
    exit /b 1
)

:: --- detener y eliminar servicio ---
sc query PrintTrackerAgent >nul 2>&1
if %errorLevel% equ 0 (
    echo Deteniendo servicio...
    nssm stop PrintTrackerAgent >nul 2>&1
    echo Eliminando servicio...
    nssm remove PrintTrackerAgent confirm >nul 2>&1
    echo [OK] Servicio eliminado
) else (
    echo [INFO] El servicio no estaba instalado
)

:: --- borrar archivos ---
if exist "C:\PrintTracker" (
    echo Borrando archivos...
    rmdir /s /q "C:\PrintTracker"
    echo [OK] Archivos eliminados
)

echo.
echo  [OK] Print Tracker desinstalado correctamente.
echo.
pause
