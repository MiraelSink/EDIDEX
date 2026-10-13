@echo off
REM ============================================================================
REM  EDIMETER - compilation de l'executable Windows
REM
REM  Produit : dist\EDIMETER.exe  (~55 Mo, autonome)
REM
REM  PyInstaller ne compile PAS vers Windows depuis Linux ou macOS : ce
REM  script doit imperativement etre execute sur Windows.
REM
REM  Usage :
REM     windows\build.bat          compile et conserve .venv
REM     windows\build.bat --clean  compile puis supprime .venv (~54 Mo sur disque)
REM ============================================================================

setlocal EnableExtensions

pushd "%~dp0.." >nul 2>&1
if errorlevel 1 goto :no_project
set "ROOT=%CD%"
popd

set "LOG=%ROOT%\windows\build.log"
set "VPY=%ROOT%\.venv\Scripts\python.exe"
set "NAME=EDIMETER"
set "CLEAN=0"
if /i "%~1"=="--clean" set "CLEAN=1"

> "%LOG%" echo EDIMETER - build %DATE% %TIME%

echo %ROOT% | findstr /b /c:"\\" >nul
if not errorlevel 1 goto :unc_path

REM ---- Le virtualenv est requis pour compiler -------------------------------
if not exist "%VPY%" goto :no_venv

echo.
echo ==== Nettoyage du cache precedent ====
rd /s /q "%ROOT%\build" >nul 2>&1
if exist "%ROOT%\build" goto :clean_failed
echo     Cache supprime.

echo.
echo ==== Compilation de %NAME%.exe ====
echo     Cela peut prendre 2 a 5 minutes.
echo.
"%VPY%" -m PyInstaller ^
    --noconfirm ^
    --onefile ^
    --windowed ^
    --name "%NAME%" ^
    --distpath "%ROOT%\dist" ^
    --workpath "%ROOT%\build" ^
    --specpath "%ROOT%\build" ^
    --paths "%ROOT%" ^
    --exclude-module tkinter ^
    --exclude-module unittest ^
    --exclude-module pydoc ^
    --exclude-module PyQt5 ^
    --exclude-module PyQt6 ^
    --exclude-module PySide2 ^
    --exclude-module numpy ^
    --exclude-module scipy ^
    --exclude-module matplotlib ^
    --exclude-module setuptools ^
    --exclude-module pip ^
    --hidden-import PySide6.QtCore ^
    --hidden-import PySide6.QtGui ^
    --hidden-import PySide6.QtWidgets ^
    "%ROOT%\run.py"
if errorlevel 1 goto :build_failed

if not exist "%ROOT%\dist\%NAME%.exe" goto :missing_exe

echo.
echo ==== Termine ====
for %%A in ("%ROOT%\dist\%NAME%.exe") do echo     Taille : %%~zA octets
echo     Sortie : dist\%NAME%.exe

REM ---- Nettoyage -----------------------------------------------------------
echo.
echo ==== Nettoyage ====
call :clean_caches

if "%CLEAN%"=="1" (
    echo     Suppression de .venv demandee par --clean...
    rd /s /q "%ROOT%\.venv" >nul 2>&1
    if exist "%ROOT%\.venv" goto :venv_locked
    echo     .venv supprime.
    echo.
    echo     Pour recompiler, relancez d'abord windows\setup.bat
    echo     ^(retelechargement de PySide6, environ 90 Mo^).
) else (
    echo     .venv conserve. Utilisez --clean pour le supprimer apres coup.
)

echo.
echo L'executable est autonome : aucune installation n'est requise
echo sur la machine cible. Testez-le en double-cliquant dessus.
echo.
echo Journal : %LOG%
echo.
pause
endlocal
exit /b 0

:clean_caches
rd /s /q "%ROOT%\build" >nul 2>&1
for /d %%D in ("%ROOT%\screeninfo_gui\__pycache__" "%ROOT%\tests\__pycache__" "%ROOT%\__pycache__") do (
    if exist "%%D" rd /s /q "%%D" >nul 2>&1
)
echo     Cache PyInstaller et __pycache__ supprimes.
goto :eof

REM --- Echots ---------------------------------------------------------------
:build_failed
echo.
echo *** ECHEC : la compilation a echoue.
echo.
echo     Le journal complet est dans : %LOG%
echo     Les dernieres lignes ci-dessous peuvent aider :
echo.
powershell -NoProfile -Command "Get-Content -Tail 25 '%LOG%'" 2>nul
echo.
pause
endlocal
exit /b 1

:missing_exe
echo.
echo *** ECHEC : dist\%NAME%.exe est absent alors que PyInstaller a reussi.
echo     Journal : %LOG%
echo.
pause
endlocal
exit /b 1

:clean_failed
echo.
echo *** ECHEC : impossible de supprimer %ROOT%\build
echo     Un fichier y est probablement verrouille par un antivirus.
echo     Fermez l'application si elle tourne, puis relancez.
echo.
pause
endlocal
exit /b 1

:venv_locked
echo.
echo *** ATTENTION : .venv n'a pas pu etre supprime entierement.
echo     Un fichier y reste verrouille (antivirus, explorateur de fichiers).
echo     Fermez les fenetres concernees, puis supprimez le dossier a la main.
echo.
pause

:no_venv
echo.
echo *** Le virtualenv est absent : impossible de compiler.
echo.
echo     Attendu : %VPY%
echo     Lancez d'abord windows\setup.bat.
echo.
pause
endlocal
exit /b 1

:unc_path
echo.
echo *** ECHEC : le projet est sur un chemin UNC.
echo.
echo     Situation : %ROOT%
echo.
echo     cmd.exe ne peut pas se placer dans un chemin UNC, et PyInstaller
echo     echoue de facon peu fiable sur un systeme de fichiers WSL.
echo     Compilez depuis une copie sur le disque Windows, par exemple :
echo         C:\Users\%USERNAME%\EDIMETER
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