"""Vérifie que les fonds de carte configurés renvoient bien des tuiles.

Utilitaire de diagnostic réseau (hors pytest, car il dépend d'Internet) :

    python tests/check_tiles.py
"""

from __future__ import annotations

import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from carto.config import resource_path  # noqa: E402

#: Tuile de test : vallée de la Seine, zoom 13.
Z, X, Y = 13, 4143, 2811
HEADERS = {"User-Agent": "Carto/0.2 (test de tuiles)"}


def extract_urls() -> dict[str, str]:
    """Extrait les gabarits d'URL des couches déclarées dans map.html."""
    html = resource_path("map.html").read_text(encoding="utf-8")
    ign_base = re.search(r'var IGN_BASE\s*=\s*((?:\s*\+?\s*"[^"]*")+);', html)
    base = "".join(re.findall(r'"([^"]*)"', ign_base.group(1))) if ign_base else ""

    urls: dict[str, str] = {}
    for name, expr in re.findall(
        r'"([^"]+)":\s*L\.tileLayer\(\s*((?:\s*\+?\s*(?:"[^"]*"|IGN_BASE))+)',
        html,
    ):
        url = ""
        for token in re.findall(r'"[^"]*"|IGN_BASE', expr):
            url += base if token == "IGN_BASE" else token[1:-1]
        urls[name] = url
    return urls


def check(url: str) -> tuple[bool, str]:
    request = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            ctype = response.headers.get("Content-Type", "")
            size = len(response.read())
            ok = response.status == 200 and ctype.startswith("image/")
            return ok, f"HTTP {response.status} {ctype} {size} octets"
    except Exception as exc:  # noqa: BLE001
        return False, f"erreur : {exc}"


def main() -> int:
    failures = 0
    for name, template in extract_urls().items():
        url = (
            template.replace("{z}", str(Z))
            .replace("{x}", str(X))
            .replace("{y}", str(Y))
        )
        ok, detail = check(url)
        print(f"{'OK  ' if ok else 'ECHEC'}  {name:<26} {detail}")
        failures += not ok
    if failures:
        print(f"\n{failures} couche(s) en échec.")
    else:
        print("\nToutes les couches répondent.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
