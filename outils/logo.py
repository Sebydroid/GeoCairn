"""Dessin du logo de Géo Cairn et fabrication de l'icône Windows.

    python outils/logo.py

Produit `geocairn/resources/geocairn.ico`, l'icône portée par l'exécutable,
les raccourcis, l'installeur et la fenêtre du programme. Le fichier produit est
versionné : ce script ne sert qu'à le refaire après une retouche du dessin, et
Pillow n'est donc pas nécessaire pour utiliser ou construire le logiciel.

Le motif — un cairn de trois pierres surmonté d'un point de position qui émet
deux ondes — vit ici en géométrie plutôt qu'en image toute faite, pour deux
raisons :

* une icône Windows contient plusieurs tailles, de 16 à 256 pixels, et un
  simple rétrécissement de la grande vers la petite donne une bouillie ;
* en dessous de 32 pixels, il n'y a plus la place pour cinq bandes séparées.
  Un second dessin, allégé à deux pierres et une seule onde, prend le relais —
  c'est la pratique courante pour les icônes d'application.

Le dessin de référence reste `geocairn/resources/logo.svg`, dont ce module
reprend les coordonnées (grille de 64 unités).
"""

from __future__ import annotations

import sys
from pathlib import Path

#: Facteur de suréchantillonnage. Pillow dessine sans lissage : on trace huit
#: fois trop grand, puis on réduit. Le lissage vient de la réduction.
SUPER = 8

#: Grille de référence du dessin, identique à celle du SVG.
GRILLE = 64

#: Pierre du cairn, et point de position avec ses ondes.
PIERRE = (124, 138, 153, 255)
SIGNAL = (224, 122, 62, 255)

#: Tailles rangées dans l'icône Windows. 16 à 48 servent à l'explorateur et à
#: la barre des tâches, 256 à l'affichage en grandes icônes et à l'installeur.
TAILLES = (16, 24, 32, 48, 64, 128, 256)

#: En dessous de cette taille, le dessin allégé prend le relais.
SEUIL_DESSIN_ALLEGE = 32


def _cercle(dessin, cx, cy, r, couleur, u):
    dessin.ellipse(
        [(cx - r) * u, (cy - r) * u, (cx + r) * u, (cy + r) * u], fill=couleur
    )


def _onde(dessin, cx, cy, r, epaisseur, couleur, u):
    """Arc de 120° ouvert vers le haut, terminé par des bouts ronds.

    `r` est le rayon de l'axe du trait, comme le veut le SVG. Pillow, lui,
    épaissit ses arcs vers l'intérieur du rectangle englobant : celui-ci est
    donc élargi d'une demi-épaisseur, faute de quoi les disques ajoutés aux
    extrémités — qui reproduisent le `stroke-linecap="round"` — déborderaient
    du trait et donneraient deux grosses billes au bout des ondes.
    """
    import math

    externe = r + epaisseur / 2
    dessin.arc(
        [
            (cx - externe) * u, (cy - externe) * u,
            (cx + externe) * u, (cy + externe) * u,
        ],
        start=210,
        end=330,
        fill=couleur,
        width=int(round(epaisseur * u)),
    )
    dx = r * math.sin(math.radians(60))
    dy = r * math.cos(math.radians(60))
    for signe in (-1, 1):
        _cercle(dessin, cx + signe * dx, cy - dy, epaisseur / 2, couleur, u)


def _pierre(dessin, x, y, largeur, hauteur, couleur, u):
    dessin.rounded_rectangle(
        [x * u, y * u, (x + largeur) * u, (y + hauteur) * u],
        radius=hauteur / 2 * u,
        fill=couleur,
    )


def dessiner(taille: int, allege: bool | None = None):
    """Rend le logo en une image RGBA carrée de `taille` pixels."""
    from PIL import Image, ImageDraw

    if allege is None:
        allege = taille < SEUIL_DESSIN_ALLEGE

    cote = taille * SUPER
    image = Image.new("RGBA", (cote, cote), (0, 0, 0, 0))
    dessin = ImageDraw.Draw(image)
    u = cote / GRILLE  # unités de la grille vers pixels de travail

    if allege:
        # Deux pierres, une onde : tout est plus gros et plus espacé, pour
        # rester lisible quand chaque bande ne pèse que deux pixels.
        _onde(dessin, 32, 26, 15, 6, SIGNAL, u)
        _cercle(dessin, 32, 26, 6.5, SIGNAL, u)
        _pierre(dessin, 19, 36, 26, 9, PIERRE, u)
        _pierre(dessin, 13, 49, 38, 10, PIERRE, u)
    else:
        _onde(dessin, 32, 23.5, 15.5, 4, SIGNAL, u)
        _onde(dessin, 32, 23.5, 9.5, 4, SIGNAL, u)
        _cercle(dessin, 32, 23.5, 4.5, SIGNAL, u)
        _pierre(dessin, 21, 30.5, 22, 7.5, PIERRE, u)
        _pierre(dessin, 17, 40.5, 30, 8, PIERRE, u)
        _pierre(dessin, 13, 51, 38, 8.5, PIERRE, u)

    return image.resize((taille, taille), Image.LANCZOS)


def construire_ico(destination: Path) -> Path:
    """Écrit l'icône Windows multi-résolutions."""
    images = [dessiner(t) for t in TAILLES]
    principale = images[-1]
    destination.parent.mkdir(parents=True, exist_ok=True)
    principale.save(
        destination,
        format="ICO",
        sizes=[(t, t) for t in TAILLES],
        append_images=images[:-1],
    )
    return destination


def planche(destination: Path) -> Path:
    """Planche de contrôle : chaque taille rendue, alignée sur une bande.

    Sert à juger le résultat à l'œil, notamment la lisibilité en 16 pixels.
    """
    from PIL import Image

    marge = 8
    largeur = sum(t + marge for t in TAILLES) + marge
    hauteur = max(TAILLES) + 2 * marge
    planche = Image.new("RGBA", (largeur, hauteur), (255, 255, 255, 255))
    x = marge
    for t in TAILLES:
        planche.paste(dessiner(t), (x, hauteur - marge - t), dessiner(t))
        x += t + marge
    planche.save(destination)
    return destination


if __name__ == "__main__":
    racine = Path(__file__).resolve().parent.parent
    try:
        import PIL  # noqa: F401
    except ImportError:
        print("Pillow est nécessaire pour refaire l'icône : pip install Pillow")
        sys.exit(1)
    cible = construire_ico(racine / "geocairn" / "resources" / "geocairn.ico")
    print(f"icône écrite : {cible}")
