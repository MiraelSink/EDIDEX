@echo off
REM ============================================================================
REM  EDIMETER - lancement de l'application
REM
REM  Utilise le virtualenv du projet (.\..\.venv). Si celui-ci est absent,
REM  lancez d'abord windows\setup.bat.
REM ============================================================================

setlocal EnableExtensions

pushd "%~dp0.." >nul 2>&1
if errorlevel 1 goto :no_project
set "ROOT=%CD%"
popd

set "VPY=%ROOT%\.venv\Scripts\python.exe"

if not exist "%VPY%" goto :no_venv

"%VPY%" "%ROOT%\run.py"
if errorlevel 1 (
    echo.
    echo L'application s'est terminee avec une erreur.
    pause
)
endlocal
exit /b 0

:no_venv
echo.
echo *** Le virtualenv est absent.
echo.
echo     Attendu : %VPY%
echo.
echo     Lancez d'abord windows\setup.bat pour installer les dependances.
echo.
pause
endlocal
exit /b 1

:no_project
echo.
echo *** Impossible d'acceder au dossier du projet.
echo.
pause
endlocal
exit /b 1