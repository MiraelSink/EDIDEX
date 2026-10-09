# Monitor_Detection — Linux

Installation et compilation. Voir `linux/README.md` pour le détail.

```bash
chmod +x linux/setup.sh   # une seule fois
./linux/setup.sh
./linux/run.sh            # lancer
./linux/build.sh --clean  # compiler puis nettoyer (53 Mo au total)
```

Prérequis de compilation : `sudo apt install binutils libpython3.13`.