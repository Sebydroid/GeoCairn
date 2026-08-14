"""Altitude des points par le service altimétrique de l'IGN.

Une trace dessinée à la main n'a aucune altitude : le GPX n'en contient que si
l'appareil qui l'a enregistrée en fournissait. Plutôt que de télécharger un
modèle numérique de terrain (le RGE ALTI complet pèse des dizaines de gigaoctets),
on interroge le service de calcul altimétrique de la Géoplateforme, gratuit et
sans clé d'accès.

    https://data.geopf.fr/altimetrie/1.0/calcul/alti/rest/elevation.json

Couverture : France métropolitaine et outre-mer. Hors de cette zone, le service
ne renvoie rien et les altitudes restent vides.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Sequence

from . import APP_SLUG, APP_VERSION
from .models import Point

SERVICE_URL = "https://data.geopf.fr/altimetrie/1.0/calcul/alti/rest/elevation.json"
RESOURCE = "ign_rge_alti_wld"

#: Au-delà, l'URL dépasse la longueur acceptée par le serveur (HTTP 414).
BATCH_SIZE = 150

#: Valeur renvoyée par le service pour un point hors couverture.
HORS_COUVERTURE = -99999.0

TIMEOUT_S = 40


class ElevationError(RuntimeError):
    """Le service altimétrique n'a pas pu être interrogé."""


def _default_fetch(url: str) -> bytes:
    request = urllib.request.Request(
        url, headers={"User-Agent": f"{APP_SLUG}/{APP_VERSION}"}
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
        return response.read()


def _batch_url(batch: Sequence[Point]) -> str:
    parametres = urllib.parse.urlencode(
        {
            "lon": "|".join(f"{p.lon:.6f}" for p in batch),
            "lat": "|".join(f"{p.lat:.6f}" for p in batch),
            "resource": RESOURCE,
            "zonly": "true",
        }
    )
    return f"{SERVICE_URL}?{parametres}"


def _parse(contenu: bytes, attendus: int) -> list[float | None]:
    try:
        donnees = json.loads(contenu)
    except json.JSONDecodeError as exc:
        raise ElevationError(f"Réponse illisible du service : {exc}") from exc

    if "error" in donnees:
        message = donnees["error"].get("description", "erreur inconnue")
        raise ElevationError(f"Service altimétrique : {message}")

    valeurs = donnees.get("elevations")
    if not isinstance(valeurs, list) or len(valeurs) != attendus:
        raise ElevationError(
            f"Réponse inattendue : {len(valeurs) if valeurs else 0} altitudes "
            f"pour {attendus} points."
        )

    resultat: list[float | None] = []
    for valeur in valeurs:
        if isinstance(valeur, dict):
            valeur = valeur.get("z")
        try:
            altitude = float(valeur)
        except (TypeError, ValueError):
            resultat.append(None)
            continue
        resultat.append(None if altitude <= HORS_COUVERTURE else altitude)
    return resultat


def fetch_elevations(
    points: Sequence[Point],
    on_progress: Callable[[int, int], bool] | None = None,
    fetch: Callable[[str], bytes] | None = None,
    batch_size: int = BATCH_SIZE,
) -> list[float | None]:
    """Altitude de chaque point, dans l'ordre. None hors couverture.

    `on_progress(faits, total)` est appelé après chaque lot ; s'il retourne
    False, le calcul s'arrête et les points restants valent None.
    `fetch` permet d'injecter un transport de test.
    """
    if not points:
        return []

    recuperer = fetch or _default_fetch
    resultats: list[float | None] = []

    for debut in range(0, len(points), batch_size):
        lot = points[debut : debut + batch_size]
        try:
            contenu = recuperer(_batch_url(lot))
        except urllib.error.HTTPError as exc:
            raise ElevationError(
                f"Service altimétrique indisponible (HTTP {exc.code})."
            ) from exc
        except OSError as exc:
            raise ElevationError(
                f"Service altimétrique injoignable : {exc}"
            ) from exc

        resultats.extend(_parse(contenu, len(lot)))

        if on_progress is not None and not on_progress(len(resultats), len(points)):
            resultats.extend([None] * (len(points) - len(resultats)))
            break

    return resultats


def apply_elevations(
    points: Sequence[Point], elevations: Sequence[float | None]
) -> list[Point]:
    """Retourne les points enrichis de l'altitude du service."""
    return [
        Point(p.lat, p.lon, p.ele, p.time, altitude)
        for p, altitude in zip(points, elevations)
    ]
