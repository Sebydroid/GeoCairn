"""Tests du service altimétrique IGN (transport simulé)."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse

import pytest

from geocairn.elevation import (
    BATCH_SIZE,
    ElevationError,
    apply_elevations,
    fetch_elevations,
)
from geocairn.models import Point

TROIS = [Point(48.930, 1.440), Point(48.931, 1.442), Point(48.932, 1.441)]


def reponse(valeurs) -> bytes:
    return json.dumps({"elevations": valeurs}).encode("utf-8")


def transport(valeurs_par_appel, urls=None):
    """Faux transport : renvoie les réponses préparées, note les URL reçues."""
    restant = list(valeurs_par_appel)

    def fetch(url: str) -> bytes:
        if urls is not None:
            urls.append(url)
        return reponse(restant.pop(0))

    return fetch


def parametres(url: str) -> dict:
    return urllib.parse.parse_qs(urllib.parse.urlparse(url).query)


# ------------------------------------------------------------------ requête


def test_altitudes_recuperees_dans_l_ordre():
    altitudes = fetch_elevations(TROIS, fetch=transport([[63.2, 72.5, 83.4]]))

    assert altitudes == [63.2, 72.5, 83.4]


def test_les_coordonnees_sont_transmises_separees_par_des_barres():
    urls = []
    fetch_elevations(TROIS, fetch=transport([[1, 2, 3]], urls))

    params = parametres(urls[0])
    assert params["lon"][0] == "1.440000|1.442000|1.441000"
    assert params["lat"][0] == "48.930000|48.931000|48.932000"
    assert params["resource"][0] == "ign_rge_alti_wld"


def test_decoupage_en_lots():
    """Au-delà d'environ 200 points, l'URL est refusée par le serveur."""
    points = [Point(48.0 + i / 1000, 1.0) for i in range(350)]
    urls = []
    fetch = transport([[10.0] * 150, [20.0] * 150, [30.0] * 50], urls)

    altitudes = fetch_elevations(points, fetch=fetch, batch_size=150)

    assert len(urls) == 3
    assert len(altitudes) == 350
    assert altitudes[0] == 10.0 and altitudes[200] == 20.0
    assert BATCH_SIZE <= 200


def test_liste_vide():
    assert fetch_elevations([], fetch=transport([])) == []


def test_points_hors_couverture():
    """Le service renvoie -99999 hors de son emprise."""
    altitudes = fetch_elevations(
        TROIS, fetch=transport([[63.2, -99999.0, 83.4]])
    )

    assert altitudes == [63.2, None, 83.4]


def test_format_detaille_accepte():
    """Le service peut répondre par des objets plutôt que des nombres."""
    def fetch(_url):
        return json.dumps(
            {"elevations": [{"z": 63.2}, {"z": 72.5}, {"z": 83.4}]}
        ).encode()

    assert fetch_elevations(TROIS, fetch=fetch) == [63.2, 72.5, 83.4]


# ------------------------------------------------------------- progression


def test_progression_rapportee():
    points = [Point(48.0 + i / 1000, 1.0) for i in range(250)]
    etapes = []

    def progression(faits, total):
        etapes.append((faits, total))
        return True

    fetch_elevations(
        points,
        on_progress=progression,
        fetch=transport([[1.0] * 100, [2.0] * 100, [3.0] * 50]),
        batch_size=100,
    )

    assert etapes == [(100, 250), (200, 250), (250, 250)]


def test_interruption_par_l_utilisateur():
    points = [Point(48.0 + i / 1000, 1.0) for i in range(250)]

    altitudes = fetch_elevations(
        points,
        on_progress=lambda faits, total: False,   # interrompt tout de suite
        fetch=transport([[1.0] * 100]),
        batch_size=100,
    )

    assert len(altitudes) == 250
    assert altitudes[0] == 1.0
    assert altitudes[100] is None   # les lots suivants n'ont pas été demandés


# ------------------------------------------------------------------ erreurs


def test_service_injoignable():
    def fetch(_url):
        raise OSError("réseau coupé")

    with pytest.raises(ElevationError, match="injoignable"):
        fetch_elevations(TROIS, fetch=fetch)


def test_erreur_http():
    def fetch(_url):
        raise urllib.error.HTTPError(_url, 414, "Too Long", {}, None)

    with pytest.raises(ElevationError, match="414"):
        fetch_elevations(TROIS, fetch=fetch)


def test_reponse_illisible():
    with pytest.raises(ElevationError, match="illisible"):
        fetch_elevations(TROIS, fetch=lambda _url: b"pas du json")


def test_erreur_rapportee_par_le_service():
    def fetch(_url):
        return json.dumps(
            {"error": {"code": "BAD_PARAMETER", "description": "longitude invalide"}}
        ).encode()

    with pytest.raises(ElevationError, match="longitude invalide"):
        fetch_elevations(TROIS, fetch=fetch)


def test_nombre_d_altitudes_incoherent():
    with pytest.raises(ElevationError, match="inattendue"):
        fetch_elevations(TROIS, fetch=transport([[63.2]]))


# ------------------------------------------------------------ application


def test_application_aux_points():
    enrichis = apply_elevations(TROIS, [63.2, None, 83.4])

    assert enrichis[0].ele_service == pytest.approx(63.2)
    assert enrichis[1].ele_service is None
    assert enrichis[2].ele_service == pytest.approx(83.4)
    # Coordonnées et altitude du fichier inchangées.
    assert enrichis[0].as_tuple() == TROIS[0].as_tuple()
    assert enrichis[0].ele is None


def test_l_altitude_du_fichier_est_preservee():
    points = [Point(48.9, 1.4, 70.0), Point(48.91, 1.41, 72.0)]

    enrichis = apply_elevations(points, [63.2, 65.0])

    assert enrichis[0].ele == pytest.approx(70.0)
    assert enrichis[0].ele_service == pytest.approx(63.2)
