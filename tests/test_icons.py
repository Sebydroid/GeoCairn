"""Tests des icônes dessinées à la volée."""

from __future__ import annotations

import pytest

from geocairn.app import create_app
from geocairn.ui.icons import BULB_OFF, BULB_ON, BULB_PARTIAL, bulb_icon


@pytest.fixture(scope="session")
def qapp():
    app = create_app(["geocairn-tests"])
    yield app
    app.processEvents()


@pytest.mark.parametrize("etat", [BULB_ON, BULB_OFF, BULB_PARTIAL])
def test_l_ampoule_produit_une_image_non_vide(qapp, etat):
    icone = bulb_icon(etat)

    assert not icone.isNull()
    pixmap = icone.pixmap(16, 16)
    assert not pixmap.isNull()
    assert pixmap.size().width() == 16

    image = pixmap.toImage()
    pixels_dessines = sum(
        1
        for y in range(image.height())
        for x in range(image.width())
        if image.pixelColor(x, y).alpha() > 0
    )
    assert pixels_dessines > 20, "l'ampoule est restée vide"


def test_les_etats_se_distinguent(qapp):
    """Allumée et éteinte doivent être visuellement différentes."""
    allumee = bulb_icon(BULB_ON).pixmap(16, 16).toImage()
    eteinte = bulb_icon(BULB_OFF).pixmap(16, 16).toImage()

    assert allumee != eteinte


def test_les_icones_sont_mises_en_cache(qapp):
    assert bulb_icon(BULB_ON) is bulb_icon(BULB_ON)
