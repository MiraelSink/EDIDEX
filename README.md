# EDIMETER — **E**D**I**D **METER**

Application portable affichant, en un clic, la **taille en pouces**, la
**marque** et le **numéro de série** de chaque écran. Thème vert, noir et
blanc, blanc dominant.

*Le nom décrit la méthode : un EDID est le bloc de 128 octets que chaque écran
publie, et l'application en tire des mesures. Elle mesure, elle ne devine pas.*

Fonctionne sous Linux et sous Windows. L'exécutable produit est autonome : ni
Python, ni installation, ni connexion requise sur la machine cible.

## Démarrage rapide

| | Installation | Lancement | Compilation |
|---|---|---|---|
| **Linux** | `./linux/setup.sh` | `./linux/run.sh` | `./linux/build.sh --clean` |
| **Windows** | `windows\setup.bat` | `windows\run.bat` | `windows\build.bat --clean` |

Guides détaillés : [`linux/README.md`](linux/README.md) et
[`windows/README.md`](windows/README.md).

## Organisation

```
EDIMETER/
├── screeninfo_gui/       code partagé, un seul exemplaire
│   ├── edid.py           analyseur EDID (128 octets)
│   ├── model.py          MonitorInfo, calcul de diagonale
│   ├── monitors_linux.py xrandr, puis /sys/class/drm, puis Qt
│   ├── monitors_windows.py  registre winreg, EnumDisplayMonitors
│   ├── theme.py          feuille de style QSS
│   └── app.py            interface PySide6
├── linux/                scripts Bash
├── windows/              scripts batch
├── tests/test_edid.py    67 tests
├── check_env.py          diagnostic des dépendances
├── run.py                point d'entrée
└── dist/                 exécutable compilé (après build)
```

`screeninfo_gui/` est commun aux deux plateformes : `edid.py`, `model.py`,
`theme.py` et `app.py` sont identiques, seuls les deux back ends diffèrent. Les
scripts de `windows/` pointent vers le dossier parent, qui est donc requis pour
compiler.

## Ce que l'application affiche

Pour chaque écran, une carte avec la diagonale en pouces en grand, la marque,
le numéro de série, la taille physique, la résolution, et des badges
`PRINCIPAL`, `SOUS LE CURSEUR`, `EDID` ou `estimé`.

Une donnée absente de l'écran est affichée `Non disponible`, jamais devinée. Un
encadré « Remarque » explique la cause lorsqu'une information manque.

### Copier les informations

Un bouton **Copier** sur chaque carte et un bouton **Tout copier** dans l'en-tête
copient vers le presse-papiers :

```
Ecran 1 - ASUS VG27A
  Marque            : ASUS
  Numero de serie   : CN0ASU1
  Diagonale         : 27.0"
  Taille physique   : 23.5 x 13.2 pouces
  Resolution        : 2560 x 1440
  Nom EDID          : ASUS VG27A
  Code fabricant    : ASUS (AUO)
  EDID brut         : 00ffffffffffff0004...   (128 octets en hexadécimal)
```

Le bloc `EDID brut` est inclus à dessein : il permet de vérifier une valeur
douteuse, et de diagnostiquer un appraisalement incorrect entre deux écrans.

## Comment la détection fonctionne

Chaque écran publie un bloc EDID de 128 octets contenant marque, référence,
numéro de série et dimensions. Le même analyseur sert aux deux plateformes.

**Marque.** L'EDID contient deux sources : un code fabricant de trois lettres,
et un descripteur de nom (0xFC) tel que `ASUS VG27A`. Le code désigne souvent
le **fabricant du panneau** — AU Optronics pour un écran ASUS, par exemple — et
non la marque qui l'a vendu. L'application privilégie donc le descripteur de nom
et conserve le code entre parenthèses quand il diffère.

**Taille.** Deux champs, dans deux unités : les paramètres de base (octets
21-22) sont en **centimètres**, le descripteur de timing (octets 12-15) en
**millimètres**. Les confondre donnait des diagonales fausses d'un facteur dix.
Les paramètres de base sont utilisés en priorité ; si les deux sources divergent
de plus de 15 %, l'application affiche un encadré d'avertissement donnant les
deux valeurs plutôt que de présenter un chiffre faux comme une certitude.

**Numéro de série.** Deux encodages coexistent, numérique (octets 12-15) et
textuel (descripteur 0xFF). Le textuel est préféré, mais les valeurs
sentinelles (`0`, `1`, une date) sont rejetées.

**Linux** — `xrandr --verbose` en priorité (position, millimètres et EDID en un
appel), puis `/sys/class/drm/card*-*/edid`, puis en dernier recours les écrans
vus par Qt avec taille estimée depuis le DPI.

**Windows** — l'EDID mis en cache dans le registre sous
`HKLM\SYSTEM\CurrentControlSet\Enum\DISPLAY\...\Device Parameters\EDID`, lu avec
`winreg`. Ce sont des clés publiques : aucun accès administrateur, aucune boîte
UAC. `EnumDisplayMonitors` fournit position et résolution. PowerShell
`Get-CimInstance` est le dernier recours.

Aucun `sudo`, aucune élévation, aucune donnée qui quitte la machine.

## Taille sur disque

| Après | Taille | Contenu |
|---|---|---|
| `setup.sh` seul | ~318 Mo | `.venv` (266 Mo, Qt) + `dist` (53 Mo) |
| `build.sh --clean` | **~53 Mo** | `dist` uniquement |

`--clean` supprime `.venv` après compilation. Le build suivant exigera de
relancer le script d'installation.

## Tests

```bash
.venv/bin/python -m unittest discover -s tests -v
```

52 tests couvrant l'analyseur EDID (séries numériques et textuelles, valeurs
sentinelles, blocs tronqués, unités cm/mm, marque du panneau contre marque
réelle), le calcul de diagonale, l'analyseur `xrandr` et l'appariement des
écrans Windows. Aucun écran ni GPU requis.

## Limites connues

- La taille EDID est celle de la **zone active** du panneau, qui diffère souvent
  du chiffre commercial : un écran 27" peut afficher 26,9".
- Certains écrans (TV, docks, hubs USB-C) ne publient pas de numéro de série.
- Quand aucun EDID n'est disponible, la taille est estimée depuis le DPI et
  signalée `estimé`.
- **Sous WSL**, marque et numéro de série sont définitivement indisponibles : les
  sorties `rdp-*` sont virtuelles et WSLg ne transmet pas l'EDID du moniteur
  physique. Ni réinstallation ni privilège administrateur n'y changent quoi que
  ce soit. Utilisez Windows ou une session Linux native.
- Sous Windows, deux écrans identiques côte à côte sont indiscernables par l'EDID
  seul ; un avertissement signale quand les numéros de série peuvent être
  permutés.
- L'exécutable fait environ 53 Mo car Qt est embarqué. Les modules Qt inutiles
  sont exclus à la compilation. Il reste dépendant des bibliothèques graphiques
  du système (`libGL`, xcb), présentes sur tout bureau standard.
- L'exécutable Windows se compile **sur Windows** : PyInstaller ne cross-compile
  pas.