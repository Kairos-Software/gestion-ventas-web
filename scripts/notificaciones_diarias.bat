@echo off
REM Corre los reportes y alertas de asistencia (mensual, semanal,
REM vencimientos, deudas por vencer, stock, cheques) y los manda por
REM mail segun lo configurado en Configuracion, seccion Notificaciones.
REM Pensado para ejecutarse una vez al dia via el Programador de
REM tareas de Windows.
REM
REM Asume el mismo layout que en desarrollo: la carpeta del
REM virtualenv (entorno) como hermana de esta carpeta del proyecto
REM (sistema-kairos). Si en el servidor de produccion el layout es
REM distinto, ajustar la ruta de PYTHON_EXE abajo.

setlocal
chcp 65001 >nul
set "PROJECT_DIR=%~dp0.."
set "PYTHON_EXE=%PROJECT_DIR%\..\entorno\Scripts\python.exe"

cd /d "%PROJECT_DIR%"
"%PYTHON_EXE%" manage.py correr_asistencia --tipo todos >> "%PROJECT_DIR%\scripts\notificaciones_diarias.log" 2>&1
endlocal
