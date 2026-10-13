@echo off
REM ============================================================================
REM  EDIMETER - installation de l'environnement de developpement
REM
REM  Installe PySide6 et PyInstaller dans un virtualenv local (.\..\.venv).
REM  Aucun droit administrateur n'est requis : rien n'est ecrit dans
REM  Program Files ni dans le registre systeme.
REM
REM  A executer depuis un terminal Windows (cmd ou PowerShell), en double-cliquant
REM  sur le fichier ou via :  windows\setup.bat
REM ============================================================================

setlocal EnableExtensions

REM ---- Repertoire du projet (un niveau au-dessus de ce script) --------------
pushd "%~dp0.." >nul 2>&1
if errorlevel 1 goto :no_project
set "ROOT=%CD%"
popd

set "LOG=%ROOT%\windows\setup.log"
set "VENV=%ROOT%\.venv"

REM ---- Journalisation -------------------------------------------------------
> "%LOG%" echo EDIMETER - setup %DATE% %TIME%
echo Journal : %LOG%

REM ---- Verification du type de chemin --------------------------------------
REM pushd echoue sur un chemin UNC (typiquement \\wsl.localhost\... depuis
REM lequel cmd.exe ne peut pas se placer). Detecte ici pour eviter un
REM diagnostic incomprehensible plus loin.
echo %ROOT% | findstr /b /c:"\\" >nul
if not errorlevel 1 goto :unc_path

echo.
echo ==== Verification de l'interpretation Python ====
call :log INFO Recherche d'un Python 3.9 ou plus...

set "PY="
REM 1. Le lanceur Python Launcher, installation par defaut de python.org
where py >nul 2>&1
if not errorlevel 1 (
    py -3 -c "import sys; sys.exit(0 if sys.version_info[:2]>=(3,9) else 1)" >nul 2>&1
    if not errorlevel 1 set "PY=py -3"
)
REM 2. python directement dans le PATH
if not defined PY (
    python -c "import sys; sys.exit(0 if sys.version_info[:2]>=(3,9) else 1)" >nul 2>&1
    if not errorlevel 1 set "PY=python"
)
REM 3. Emplacement par defaut quand "Add python.exe to PATH" n'est pas coche,
REM    cas tres frequent.
if not defined PY (
    for /f "delims=" %%P in ('dir /b /o-n "%LocalAppData%\Programs\Python\python.exe" "%LocalAppData%\Programs\Python\Python3*\python.exe" 2^>nul') do (
        "%%~fP" -c "import sys; sys.exit(0 if sys.version_info[:2]>=(3,9) else 1)" >nul 2>&1
        if not errorlevel 1 (
            set "PY=%%~fP"
            goto :found_python
        )
    )
)

:found_python
if not defined PY goto :no_python
call :log OK Interpreteur trouve : %PY%
echo     Trouve : %PY%
%PY% -V
goto :make_venv

:no_python
call :log KO Aucun Python 3.9+ detecte
echo.
echo *** ECHEC : Python 3.9 ou plus est introuvable.
echo.
echo     Emplacements recherches :
echo       - py -3                        ^(lanceur Python^)
echo       - python                       ^(PATH systeme^)
echo       - %%LocalAppData%%\Programs\Python
echo.
echo     Installez Python 3.9 ou plus depuis :
echo       https://www.python.org/downloads/
echo.
echo     IMPORTANT : a l'installation, cochez la case
echo     "Add python.exe to PATH". Sans cela Python reste invisible ici.
echo.
echo     Ensuite, relancez setup.bat. Aucune administration n'est necessaire.
echo.
echo     Details : %LOG%
pause
exit /b 1

:unc_path
call :log KO Chemin refuse : %ROOT%
echo.
echo *** ECHEC : le projet est sur un chemin UNC.
echo.
echo     Situation : %ROOT%
echo.
echo     cmd.exe ne peut pas utiliser un chemin UNC comme repertoire
echo     courant, et le systeme de fichiers WSL (\\wsl.localhost\...)
echo     est concerne. Compiler et installer depuis la est peu fiable.
echo.
echo     Solution : copiez le dossier EDIMETER sur le disque Windows,
echo     par exemple :
echo.
echo         C:\Users\%USERNAME%\EDIMETER
echo.
echo     Puis relancez setup.bat depuis ce nouvel emplacement.
echo.
echo     Details : %LOG%
pause
exit /b 1

:no_project
echo.
echo *** ECHEC : impossible d'acceder au dossier du projet.
echo.
pause
exit /b 1

REM ============================================================================
:make_venv
echo.
echo ==== Creation du virtualenv ====
if exist "%VENV%\Scripts\python.exe" (
    echo     Deja present, conserve.
) else (
    call :log INFO Creation de %VENV%
    %PY% -m venv "%VENV%"
    if errorlevel 1 goto :venv_failed
)

set "VPY=%VENV%\Scripts\python.exe"
if not exist "%VPY%" goto :venv_failed

echo.
echo ==== Amorcage de pip ====
"%VPY%" -m pip --version >nul 2>&1
if errorlevel 1 (
    echo     pip absent du venv, amorcage via ensurepip...
    call :log INFO pip absent, ensurepip
    "%VPY%" -m ensurepip --upgrade
    if errorlevel 1 goto :pip_failed
)
call :log OK pip disponible

echo.
echo ==== Installation de PySide6 et PyInstaller ====
echo     Cela peut prendre plusieurs minutes au premier lancement.
"%VPY%" -m pip install --upgrade pip
if errorlevel 1 goto :pip_failed
"%VPY%" -m pip install -r "%ROOT%\requirements.txt"
if errorlevel 1 goto :pip_failed
call :log OK dependances installees

echo.
echo ==== Verification finale ====
"%VPY%" "%ROOT%\check_env.py"
if errorlevel 1 (
    echo     ^(des dependances facultatives peuvent manquer^)
)

echo.
echo ==== Termine ====
echo     Lancez l'application avec :  windows\run.bat
echo     Compilez avec             :  windows\build.bat
echo.
echo     Details : %LOG%
echo.
pause
endlocal
exit /b 0

REM ============================================================================
:venv_failed
call :log KO Echec de la creation du virtualenv
echo.
echo *** ECHEC : le virtualenv n'a pas pu etre cree dans :
echo     %VENV%
echo.
echo     Cause probable : un antivirus ou une politique de groupe bloque
echo     l'ecriture de scripts dans ce dossier.
echo.
echo     Details : %LOG%
pause
exit /b 1

:pip_failed
call :log KO Echec de l'installation des dependances
echo.
echo *** ECHEC : l'installation de PySide6 ou PyInstaller a echoue.
echo.
echo     Verifiez votre connexion internet, puis relancez setup.bat.
echo     Le journal complet est dans : %LOG%
echo.
pause
exit /b 1

REM ---------------------------------------------------------------------------
:log
REM Ecrit une ligne horodatee dans le journal, en plus de la console.
echo [%DATE% %TIME%] %~1 %~2>> "%LOG%"
goto :eof