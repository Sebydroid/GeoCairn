"""Calculs de l'impression : formats de papier, échelle, emprise au sol.

Rien ici ne dépend de Qt : la mise en page et le rendu de la carte s'appuient
sur ces fonctions, que les tests vérifient à part.

La carte est en projection Web Mercator, comme Leaflet. Une échelle n'y est
exacte qu'à une latitude donnée : on la règle au centre de la page. Sur les
quelques kilomètres d'une feuille, l'écart d'un bord à l'autre reste bien en
deçà de ce que l'œil perçoit (moins de 0,2 % pour une carte au 1 : 25 000).
"""

from __future__ import annotations

import math
import re

#: Rayon de la sphère de Web Mercator (EPSG:3857), celui qu'emploie Leaflet.
RAYON_MERCATOR_M = 6378137.0

#: Côté d'une tuile, en pixels CSS.
TUILE_PX = 256

POUCE_MM = 25.4

#: Formats de papier proposés, en millimètres (largeur, hauteur) en portrait.
FORMATS = {
    "A4": (210.0, 297.0),
    "A3": (297.0, 420.0),
    "A5": (148.0, 210.0),
    "Lettre US": (215.9, 279.4),
}
FORMAT_DEFAUT = "A4"

PORTRAIT = "portrait"
PAYSAGE = "paysage"
ORIENTATION_DEFAUT = PAYSAGE

#: Échelles proposées d'emblée ; l'utilisateur peut en saisir une autre.
ECHELLES = (5000, 10000, 15000, 20000, 25000, 50000, 100000, 250000)
ECHELLE_DEFAUT = 25000

#: Bornes d'une échelle saisie à la main. En deçà du 1 : 5 000, les fonds de
#: carte n'ont plus de tuiles assez détaillées ; au-delà du 1 : 1 000 000, une
#: randonnée n'occupe plus qu'un point sur la feuille.
ECHELLE_MIN = 5000
ECHELLE_MAX = 1000000

#: Marge autour de la page. Les imprimantes de bureau ne savent pas imprimer
#: jusqu'au bord ; 10 mm passent partout.
MARGE_MM = 10.0

#: Hauteur du bandeau placé sous la carte : titre, échelle, sources.
BANDEAU_MM = 14.0

#: Finesse du rendu de la carte, en pixels CSS par pouce. Plus haut, les
#: tuiles sont plus détaillées mais leurs écritures, dessinées pour l'écran,
#: deviennent minuscules sur le papier ; 150 garde les noms lisibles.
RESOLUTION_DPI = 150.0

#: Sources à citer sous la carte, par fond (mêmes noms que map.html).
ATTRIBUTIONS = {
    "Plan (OpenStreetMap)": "© les contributeurs d'OpenStreetMap",
    "Aérienne / Satellite": "© Esri, Maxar, Earthstar Geographics",
    "IGN Plan": "© IGN – Géoplateforme",
    "IGN Carte topographique": "© IGN – Géoplateforme",
    "Photos aériennes IGN": "© IGN – Géoplateforme",
}


def dimensions_page(format_papier: str, orientation: str) -> tuple[float, float]:
    """Largeur et hauteur de la feuille, en millimètres."""
    largeur, hauteur = FORMATS[format_papier]
    if orientation == PAYSAGE:
        return hauteur, largeur
    return largeur, hauteur


def zone_carte_mm(
    largeur_utile_mm: float,
    hauteur_utile_mm: float,
    bandeau_mm: float = BANDEAU_MM,
) -> tuple[float, float]:
    """Place laissée à la carte dans la zone imprimable, bandeau déduit."""
    return largeur_utile_mm, max(0.0, hauteur_utile_mm - bandeau_mm)


def zone_carte_format(
    format_papier: str, orientation: str, marge_mm: float = MARGE_MM
) -> tuple[float, float]:
    """Place laissée à la carte sur une feuille donnée, marges déduites."""
    largeur, hauteur = dimensions_page(format_papier, orientation)
    return zone_carte_mm(largeur - 2 * marge_mm, hauteur - 2 * marge_mm)


def emprise_terrain(
    largeur_mm: float, hauteur_mm: float, echelle: int
) -> tuple[float, float]:
    """Distance au sol couverte par un rectangle de papier, en mètres."""
    return largeur_mm * echelle / 1000.0, hauteur_mm * echelle / 1000.0


def metres_par_pixel(zoom: float, latitude: float) -> float:
    """Distance au sol représentée par un pixel CSS de Leaflet."""
    equateur = 2 * math.pi * RAYON_MERCATOR_M / TUILE_PX
    return equateur * math.cos(math.radians(latitude)) / (2 ** zoom)


def zoom_pour_echelle(
    echelle: int, latitude: float, dpi: float = RESOLUTION_DPI
) -> float:
    """Niveau de zoom Leaflet (fractionnaire) qui donne l'échelle voulue.

    Un pixel CSS doit représenter au sol `echelle` fois sa taille sur le
    papier, soit `echelle × 25,4 mm / dpi`.
    """
    voulu = echelle * POUCE_MM / 1000.0 / dpi
    return math.log2(metres_par_pixel(0, latitude) / voulu)


def taille_pixels(
    largeur_mm: float, hauteur_mm: float, dpi: float = RESOLUTION_DPI
) -> tuple[int, int]:
    """Taille, en pixels CSS, d'un rectangle de papier rendu à `dpi`."""
    return (
        max(1, round(largeur_mm * dpi / POUCE_MM)),
        max(1, round(hauteur_mm * dpi / POUCE_MM)),
    )


def emprise_des_bornes(
    sud: float, ouest: float, nord: float, est: float
) -> tuple[float, float, float, float]:
    """Centre et dimensions au sol d'un rectangle géographique.

    Retourne (latitude, longitude, largeur_m, hauteur_m). Le calcul suit la
    projection de la carte : le centre est pris au milieu en Mercator, et les
    distances ramenées à l'échelle de sa latitude, comme lors du rendu.
    """
    def y_mercator(lat: float) -> float:
        return RAYON_MERCATOR_M * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))

    y_sud, y_nord = y_mercator(sud), y_mercator(nord)
    y_centre = (y_sud + y_nord) / 2
    lat_centre = math.degrees(2 * math.atan(math.exp(y_centre / RAYON_MERCATOR_M)) - math.pi / 2)
    facteur = math.cos(math.radians(lat_centre))

    largeur = math.radians(est - ouest) * RAYON_MERCATOR_M * facteur
    hauteur = (y_nord - y_sud) * facteur
    return lat_centre, (ouest + est) / 2, largeur, hauteur


def echelle_pour_emprise(
    largeur_m: float,
    hauteur_m: float,
    largeur_mm: float,
    hauteur_mm: float,
    echelles=ECHELLES,
    aisance: float = 1.1,
) -> int:
    """Plus grande échelle usuelle où tient un rectangle au sol.

    `aisance` laisse un peu d'air autour : une trace collée au bord de la
    feuille se lit mal. Si rien ne suffit, la plus petite échelle est rendue.
    """
    for echelle in sorted(echelles):
        largeur, hauteur = emprise_terrain(largeur_mm, hauteur_mm, echelle)
        if largeur >= largeur_m * aisance and hauteur >= hauteur_m * aisance:
            return echelle
    return max(echelles)


def format_echelle(echelle: int) -> str:
    """« 1 : 25 000 », avec les milliers séparés à la française."""
    return "1 : " + f"{int(echelle):,}".replace(",", " ")


def lire_echelle(texte: str) -> int | None:
    """Échelle saisie librement : « 25000 », « 1:25 000 », « 1/25000 »…

    Retourne None si le texte n'est pas une échelle acceptable.
    """
    # \s couvre aussi les espaces insécables.
    propre = re.sub(r"[\s.]", "", texte or "")
    correspondance = re.fullmatch(r"(?:1[:/])?(\d+)", propre)
    if not correspondance:
        return None
    echelle = int(correspondance.group(1))
    if not ECHELLE_MIN <= echelle <= ECHELLE_MAX:
        return None
    return echelle


def format_distance(metres: float) -> str:
    """« 500 m », « 2 km », « 1,5 km »."""
    if metres < 1000:
        return f"{metres:.0f} m"
    kilometres = metres / 1000
    if kilometres == int(kilometres):
        return f"{int(kilometres)} km"
    return f"{kilometres:.1f} km".replace(".", ",")


def format_emprise(largeur_m: float, hauteur_m: float) -> str:
    """« 6,7 × 4,5 km » : ce que couvre la feuille sur le terrain."""
    if max(largeur_m, hauteur_m) < 1000:
        return f"{largeur_m:.0f} × {hauteur_m:.0f} m"
    return (
        f"{largeur_m / 1000:.1f} × {hauteur_m / 1000:.1f} km".replace(".", ",")
    )


def barre_echelle(echelle: int, longueur_max_mm: float) -> tuple[float, float]:
    """Longueur ronde d'une barre d'échelle : (mètres, millimètres).

    La barre la plus longue en 1, 2 ou 5 × 10ⁿ mètres qui tienne dans
    `longueur_max_mm` sur le papier.
    """
    max_metres = longueur_max_mm * echelle / 1000.0
    puissance = 10 ** math.floor(math.log10(max_metres))
    metres = puissance
    for facteur in (1, 2, 5):
        if facteur * puissance <= max_metres:
            metres = facteur * puissance
    return metres, metres * 1000.0 / echelle
