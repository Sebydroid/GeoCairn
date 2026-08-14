"""Vérifie que l'exécutable construit démarre et trouve ses ressources.

    python tests/check_executable.py [chemin/vers/GeoCairn.exe]

Lance le programme livré dans un répertoire de données isolé, le laisse
s'installer quelques secondes, puis contrôle qu'il a bien créé sa base et qu'il
répond toujours. Diagnostic hors pytest : il dépend d'une construction
préalable.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from geocairn.config import DB_FILENAME, ENV_DATA_DIR  # noqa: E402

RACINE = Path(__file__).resolve().parent.parent
DEFAUT = RACINE / "dist" / "GeoCairn" / "GeoCairn.exe"
ATTENTE_S = 25


def main() -> int:
    executable = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAUT
    if not executable.is_file():
        print(f"exécutable absent : {executable}", flush=True)
        print("construire d'abord : pyinstaller geocairn.spec --noconfirm", flush=True)
        return 1

    donnees = Path(tempfile.mkdtemp(prefix="geocairn-exe-"))
    environnement = dict(os.environ, **{ENV_DATA_DIR: str(donnees)})

    print(f"exécutable : {executable}", flush=True)
    print(f"données    : {donnees}", flush=True)

    processus = subprocess.Popen(
        [str(executable)],
        env=environnement,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    base = donnees / DB_FILENAME
    debut = time.perf_counter()
    while time.perf_counter() - debut < ATTENTE_S:
        if base.is_file() and base.stat().st_size > 0:
            break
        if processus.poll() is not None:
            break
        time.sleep(0.5)

    vivant = processus.poll() is None
    duree = time.perf_counter() - debut

    print(f"base créée : {base.is_file()} "
          f"({base.stat().st_size if base.is_file() else 0} octets)", flush=True)
    print(f"démarrage  : {duree:.1f} s", flush=True)
    print(f"toujours actif : {vivant}", flush=True)

    if vivant:
        # Laisser la carte se charger avant de refermer.
        time.sleep(6)
        vivant = processus.poll() is None
        print(f"actif après chargement de la carte : {vivant}", flush=True)
        processus.terminate()
        try:
            processus.wait(timeout=10)
        except subprocess.TimeoutExpired:
            processus.kill()
    else:
        sortie = processus.stdout.read().decode("utf-8", "replace") if processus.stdout else ""
        print("--- sortie du programme ---", flush=True)
        print(sortie[-2000:], flush=True)

    # Les données doivent être là où on les attend, et nulle part ailleurs.
    dans_installation = list(executable.parent.rglob(DB_FILENAME))
    print(f"base dans le dossier d'installation : {dans_installation}", flush=True)

    ok = base.is_file() and vivant and not dans_installation
    print("\nRESULTAT :", "exécutable fonctionnel" if ok else "ANOMALIE", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
