# Monitor_Detection sous Windows

## Prérequis : Python

Python **n'est pas fourni** avec Windows. Installez Python 3.9 ou plus depuis
<https://www.python.org/downloads/>.

Cochez impérativement la case **« Add python.exe to PATH »** à l'installation.
Sans elle, `setup.bat` ne trouve pas Python et le signale clairement.

## Où installer le projet

**Ne compilez pas depuis `\\wsl.localhost\...`.** `cmd.exe` ne peut pas se placer
dans un chemin UNC, et PyInstaller échoue de façon peu fiable sur le système de
fichiers WSL.

Copiez le dossier sur le disque Windows, par exemple :

```
C:\Users\<votre_nom>\Monitor_Detection
```

## Installation

Double-cliquez sur `windows\setup.bat`, ou dans une invite de commandes :

```bat
cd C:\Users\<votre_nom>\Monitor_Detection
windows\setup.bat
```

Un virtualenv est créé dans `.venv\` à la racine du projet. Rien n'est écrit
dans `Program Files`, aucun droit administrateur n'est requis.

Si une fenêtre semble se fermer aussitôt, ce n'est plus le cas : les scripts
attendent désormais une frappe et écrivent un journal dans `windows\setup.log`.
En cas d'échec, ce journal contient la cause exacte.

## Lancer l'application

Double-cliquez sur `windows\run.bat`.

Un bouton, **Analyser mes écrans**. Une carte apparaît par écran détecté.

## Compiler l'exécutable

```bat
windows\build.bat
windows\build.bat --clean
```

Résultat : `dist\Monitor_Detection.exe`, environ 53 Mo, autonome.

**PyInstaller ne compile pas vers Windows depuis Linux ni macOS.** Ce script
doit être exécuté sur Windows.

`--clean` supprime aussi `.venv\` après compilation ; le build suivant exigera
de relancer `setup.bat`.

## Ce que l'application lit

- L'EDID depuis le registre : `HKLM\SYSTEM\CurrentControlSet\Enum\DISPLAY\`
- La position et la résolution via `EnumDisplayMonitors`

Ce sont des clés publiques : **aucun accès administrateur, aucune boîte UAC**.
En dernier recours, PowerShell `Get-CimInstance` est interrogé.

## Résolution de problèmes

| Symptôme | Cause | Solution |
|---|---|---|
| « Python introuvable » | Python absent, ou PATH non configuré | Installer depuis python.org **avec** *Add python.exe to PATH* |
| « le projet est sur un chemin UNC » | Lancement depuis `\\wsl.localhost\...` | Copier le projet vers `C:\Users\<votre_nom>\` |
| « le virtualenv est absent » | `setup.bat` non exécuté | Lancer `windows\setup.bat` |
| Antivirus bloque la création | Politique de sécurité | Autoriser le dossier, ou désactiver la protection en temps réel le temps du build |

Dans tous les cas, `windows\setup.log` et `windows\build.log` contiennent le
détail des étapes qui ont échoué.