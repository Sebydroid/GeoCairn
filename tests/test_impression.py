"""Impression de la carte : format de la feuille, échelle, mise en page, PDF.

Ce que ces tests protègent avant tout : l'échelle. Une carte annoncée au
1 : 25 000 doit l'être vraiment, sans quoi les distances mesurées à la règle
sur la feuille trompent le randonneur. Elle est vérifiée de bout en bout, en
mesurant dans Leaflet la distance au sol que couvre la carte rendue.
"""

from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QColor, QImage, QKeySequence, QPainter
from PyQt6.QtPdf import QPdfDocument
from PyQt6.QtWidgets import QToolBar
from PyQt6 import sip

from geocairn.app import create_app
from geocairn.impression import (
    BANDEAU_MM,
    ECHELLES,
    MARGE_MM,
    PAYSAGE,
    PORTRAIT,
    RESOLUTION_DPI,
    barre_echelle,
    dimensions_page,
    echelle_pour_emprise,
    emprise_des_bornes,
    emprise_terrain,
    format_distance,
    format_echelle,
    format_emprise,
    lire_echelle,
    metres_par_pixel,
    taille_pixels,
    zone_carte_format,
    zoom_pour_echelle,
)
from geocairn.models import Point
from geocairn.ui.main_window import (
    CLE_IMPRESSION_ECHELLE,
    CLE_IMPRESSION_FORMAT,
    CLE_IMPRESSION_ORIENTATION,
    MainWindow,
)
from geocairn.ui.print_dialog import ReglagesImpression, peindre_page
from geocairn.ui.toolbar_icons import toolbar_icon
from tests.test_ui import run_js_sync, wait_for

# ------------------------------------------------------------------ calculs


def test_dimensions_des_formats():
    assert dimensions_page("A4", PORTRAIT) == (210.0, 297.0)
    assert dimensions_page("A4", PAYSAGE) == (297.0, 210.0)
    assert dimensions_page("A3", PAYSAGE) == (420.0, 297.0)


def test_zone_de_la_carte_deduit_marges_et_bandeau():
    largeur, hauteur = zone_carte_format("A4", PAYSAGE)

    assert largeur == pytest.approx(297 - 2 * MARGE_MM)
    assert hauteur == pytest.approx(210 - 2 * MARGE_MM - BANDEAU_MM)


def test_emprise_au_sol():
    # 1 mm au 1 : 25 000 couvre 25 m.
    assert emprise_terrain(100, 40, 25000) == pytest.approx((2500, 1000))


def test_metres_par_pixel_a_l_equateur():
    # Zoom 0 : toute la circonférence sur une tuile de 256 pixels.
    assert metres_par_pixel(0, 0) == pytest.approx(156543.034, rel=1e-6)
    assert metres_par_pixel(1, 0) == pytest.approx(156543.034 / 2, rel=1e-6)
    assert metres_par_pixel(0, 60) == pytest.approx(156543.034 / 2, rel=1e-6)


@pytest.mark.parametrize("echelle", ECHELLES)
@pytest.mark.parametrize("latitude", [0.0, 43.5, 48.93, 60.0])
def test_le_zoom_calcule_donne_exactement_l_echelle(echelle, latitude):
    zoom = zoom_pour_echelle(echelle, latitude, 150)
    # Un pixel à 150 ppp mesure 25,4 / 150 mm sur le papier.
    attendu = echelle * 25.4 / 150 / 1000
    assert metres_par_pixel(zoom, latitude) == pytest.approx(attendu, rel=1e-9)


def test_moitie_d_echelle_un_zoom_de_plus():
    ecart = zoom_pour_echelle(12500, 45) - zoom_pour_echelle(25000, 45)
    assert ecart == pytest.approx(1.0)


def test_zoom_reste_dans_les_limites_des_fonds_de_carte():
    """Les fonds s'arrêtent au zoom 18 : au-delà, Leaflet fausserait l'échelle."""
    for latitude in (0.0, 45.0):
        assert zoom_pour_echelle(5000, latitude, RESOLUTION_DPI) <= 18


def test_taille_en_pixels():
    assert taille_pixels(25.4, 50.8, 150) == (150, 300)


@pytest.mark.parametrize(
    "texte, attendu",
    [
        ("25000", 25000),
        ("1:25000", 25000),
        ("1 : 25 000", 25000),
        ("1/50000", 50000),
        ("1:25.000", 25000),
        (" 10 000 ", 10000),
        ("1 : 25 000", 25000),   # espaces insécables
        ("", None),
        ("abc", None),
        ("2:25000", None),
        ("1:100", None),         # trop détaillée pour les fonds de carte
        ("1:5000000", None),
        ("-25000", None),
    ],
)
def test_lecture_d_une_echelle_saisie(texte, attendu):
    assert lire_echelle(texte) == attendu


@pytest.mark.parametrize("echelle", ECHELLES)
def test_une_echelle_affichee_se_relit(echelle):
    assert lire_echelle(format_echelle(echelle)) == echelle


def test_format_des_textes():
    assert format_echelle(25000) == "1 : 25 000"
    assert format_echelle(250000) == "1 : 250 000"
    assert format_distance(500) == "500 m"
    assert format_distance(2000) == "2 km"
    assert format_distance(2500) == "2,5 km"
    assert format_emprise(6925, 4400) == "6,9 × 4,4 km"
    assert format_emprise(500, 300) == "500 × 300 m"


@pytest.mark.parametrize(
    "echelle, maxi, metres",
    [(25000, 50, 1000), (50000, 50, 2000), (10000, 50, 500), (20000, 50, 1000)],
)
def test_barre_d_echelle_ronde(echelle, maxi, metres):
    obtenus, longueur_mm = barre_echelle(echelle, maxi)

    assert obtenus == metres
    assert longueur_mm <= maxi
    # La barre dit vrai : sa longueur sur le papier, à l'échelle, fait bien
    # la distance annoncée.
    assert longueur_mm * echelle / 1000 == pytest.approx(metres)


def test_echelle_ajustee_a_une_emprise():
    zone = zone_carte_format("A4", PAYSAGE)   # 277 × 176 mm

    # Avec 10 % d'aisance, 5,2 × 3,3 km demandent 5,7 × 3,6 km : trop pour le
    # 1 : 20 000 (5,5 × 3,5 km), assez pour le 1 : 25 000 (6,9 × 4,4 km).
    assert echelle_pour_emprise(5200, 3300, *zone) == 25000
    assert echelle_pour_emprise(5000, 3000, *zone) == 20000
    # Trop grand pour tout : la plus petite échelle.
    assert echelle_pour_emprise(1e7, 1e7, *zone) == max(ECHELLES)


def test_emprise_des_bornes_autour_de_l_equateur():
    lat, lon, largeur, hauteur = emprise_des_bornes(-1, 10, 1, 12)

    assert lat == pytest.approx(0, abs=1e-9)
    assert lon == pytest.approx(11)
    assert largeur == pytest.approx(math.radians(2) * 6378137, rel=1e-9)
    assert hauteur == pytest.approx(math.radians(2) * 6378137, rel=1e-3)


def test_emprise_des_bornes_en_france():
    """À 49° de latitude, un degré de longitude fait environ 73 km."""
    _lat, _lon, largeur, _hauteur = emprise_des_bornes(48.9, 1.0, 49.0, 2.0)
    assert largeur == pytest.approx(73_000, rel=0.01)


# --------------------------------------------------------------- interface


@pytest.fixture(scope="session")
def qapp():
    application = create_app(["geocairn-tests"])
    yield application
    application.processEvents()


@pytest.fixture
def fenetre(db, qapp):
    window = MainWindow(db=db)
    window.resize(1100, 750)
    window.show()
    assert wait_for(lambda: window.map_view.is_ready), "carte non chargée"
    yield window
    window.close()


@pytest.fixture
def trace_affichee(fenetre):
    """Une trace d'environ 2 km du nord au sud, affichée sur la carte."""
    points = [Point(48.93 - i * 0.002, 1.44 + (i % 2) * 0.001) for i in range(10)]
    track_id = fenetre.db.create_track("Boucle de la Seine", points=points)
    fenetre.tree_panel.refresh()
    fenetre.show_track(track_id)
    return track_id


def cadre_sur_la_carte(fenetre):
    return run_js_sync(fenetre.map_view, "geocairn.printFrameBounds()")


def largeur_du_cadre_m(fenetre) -> float:
    """Largeur au sol du cadre, mesurée par Leaflet à la latitude du centre."""
    return run_js_sync(
        fenetre.map_view,
        "(function () { var b = geocairn.printFrameBounds();"
        " var lat = (b[0][0] + b[1][0]) / 2;"
        " return map.distance([lat, b[0][1]], [lat, b[1][1]]); })()",
    )


def test_icone_d_impression_dessinee(qapp):
    image = toolbar_icon("imprimer").pixmap(22, 22).toImage()
    dessines = sum(
        1
        for y in range(image.height())
        for x in range(image.width())
        if image.pixelColor(x, y).alpha() > 0
    )
    assert dessines > 40


def test_action_imprimer_dans_la_barre_et_le_menu(fenetre):
    assert fenetre.action_print.shortcut() == QKeySequence(
        QKeySequence.StandardKey.Print
    )
    barre = fenetre.findChild(QToolBar)
    assert fenetre.action_print in barre.actions()
    menu_fichier = fenetre.menuBar().actions()[0].menu()
    assert fenetre.action_print in menu_fichier.actions()


def test_ouvrir_montre_le_cadre_de_la_feuille(fenetre):
    dialogue = fenetre.ouvrir_impression()

    assert dialogue.isVisible()
    assert not dialogue.isModal(), "il faut pouvoir déplacer la carte"
    assert wait_for(lambda: cadre_sur_la_carte(fenetre) is not None, 5000)

    # A4 paysage au 1 : 25 000 : 277 mm de carte, soit 6 925 m au sol.
    reglages = dialogue.reglages()
    assert (reglages.format_papier, reglages.orientation, reglages.echelle) == (
        "A4", PAYSAGE, 25000,
    )
    assert largeur_du_cadre_m(fenetre) == pytest.approx(6925, rel=0.005)
    assert dialogue.libelle_emprise.text() == "6,9 × 4,4 km"


def test_la_boite_ne_cache_pas_le_centre_de_la_carte(fenetre):
    """Le cadre est au centre de la carte : la boîte doit le laisser voir."""
    dialogue = fenetre.ouvrir_impression()
    carte = fenetre.map_view
    centre = carte.mapToGlobal(carte.rect().center())

    assert not dialogue.frameGeometry().contains(centre)


def test_une_seule_boite_a_la_fois(fenetre):
    premiere = fenetre.ouvrir_impression()
    assert fenetre.ouvrir_impression() is premiere


def test_changer_d_echelle_redimensionne_le_cadre(fenetre):
    dialogue = fenetre.ouvrir_impression()
    dialogue.set_echelle(50000)

    assert wait_for(
        lambda: abs(largeur_du_cadre_m(fenetre) - 13850) < 70, 5000
    ), "le cadre n'a pas suivi le passage au 1 : 50 000"


def test_changer_de_format_redimensionne_le_cadre(fenetre):
    dialogue = fenetre.ouvrir_impression()
    dialogue.choix_format.setCurrentText("A3")
    dialogue.choix_orientation.setCurrentIndex(
        dialogue.choix_orientation.findData(PORTRAIT)
    )

    # A3 portrait : 297 − 20 = 277 mm de large, comme l'A4 paysage.
    assert dialogue.reglages().zone_carte() == pytest.approx((277, 400 - BANDEAU_MM))
    assert wait_for(
        lambda: abs(largeur_du_cadre_m(fenetre) - 6925) < 35, 5000
    )


def test_echelle_illisible_bloque_l_impression(fenetre):
    dialogue = fenetre.ouvrir_impression()
    dialogue.choix_echelle.setCurrentText("n'importe quoi")

    assert dialogue.reglages() is None
    assert not dialogue.bouton_imprimer.isEnabled()
    assert not dialogue.bouton_pdf.isEnabled()
    assert "illisible" in dialogue.libelle_emprise.text()
    assert wait_for(lambda: cadre_sur_la_carte(fenetre) is None, 5000)

    dialogue.choix_echelle.setCurrentText("1:10000")
    assert dialogue.bouton_imprimer.isEnabled()


def test_fermer_retire_le_cadre_et_retient_les_reglages(fenetre, qapp):
    dialogue = fenetre.ouvrir_impression()
    dialogue.choix_format.setCurrentText("A3")
    dialogue.choix_orientation.setCurrentIndex(
        dialogue.choix_orientation.findData(PORTRAIT)
    )
    dialogue.set_echelle(15000)
    dialogue.close()
    qapp.processEvents()

    assert fenetre.dialogue_impression is None
    assert wait_for(lambda: cadre_sur_la_carte(fenetre) is None, 5000)
    assert fenetre.db.get_meta(CLE_IMPRESSION_FORMAT) == "A3"
    assert fenetre.db.get_meta(CLE_IMPRESSION_ORIENTATION) == PORTRAIT
    assert fenetre.db.get_meta(CLE_IMPRESSION_ECHELLE) == "15000"

    reouverte = fenetre.ouvrir_impression()
    assert reouverte is not dialogue
    assert reouverte.reglages() == ReglagesImpression("A3", PORTRAIT, 15000)


def test_echap_retire_aussi_le_cadre(fenetre, qapp):
    dialogue = fenetre.ouvrir_impression()
    assert wait_for(lambda: cadre_sur_la_carte(fenetre) is not None, 5000)

    dialogue.reject()
    qapp.processEvents()

    assert fenetre.dialogue_impression is None
    assert wait_for(lambda: cadre_sur_la_carte(fenetre) is None, 5000)


def test_reglages_enregistres_invalides_ignores(fenetre):
    fenetre.db.set_meta(CLE_IMPRESSION_FORMAT, "B12")
    fenetre.db.set_meta(CLE_IMPRESSION_ORIENTATION, "de travers")
    fenetre.db.set_meta(CLE_IMPRESSION_ECHELLE, "beaucoup")

    dialogue = fenetre.ouvrir_impression()
    assert dialogue.reglages() == ReglagesImpression("A4", PAYSAGE, 25000)


def test_titre_propose_d_apres_la_trace_affichee(fenetre, trace_affichee):
    dialogue = fenetre.ouvrir_impression()
    assert dialogue.champ_titre.text() == "Boucle de la Seine"


def test_cadrer_sur_les_traces(fenetre, trace_affichee):
    dialogue = fenetre.ouvrir_impression()
    assert dialogue.bouton_cadrer.isEnabled()

    assert dialogue.cadrer_sur_les_traces()

    # La trace file du nord au sud (2 km sur 70 m) : le portrait l'emporte,
    # et elle tient entière au 1 : 10 000 (1,9 × 2,6 km).
    reglages = dialogue.reglages()
    assert reglages.orientation == PORTRAIT
    assert reglages.echelle == 10000
    lat, lon = fenetre.centre_carte
    assert lat == pytest.approx(48.921, abs=1e-3)
    assert lon == pytest.approx(1.4405, abs=1e-3)

    bornes = None

    def cadre_centre():
        nonlocal bornes
        bornes = cadre_sur_la_carte(fenetre)
        return bornes is not None and abs((bornes[0][0] + bornes[1][0]) / 2 - lat) < 1e-3

    assert wait_for(cadre_centre, 5000)
    # Toute la trace est dans le cadre.
    points = fenetre.db.get_track(trace_affichee, with_points=True).points
    for p in points:
        assert bornes[0][0] < p.lat < bornes[1][0]
        assert bornes[0][1] < p.lon < bornes[1][1]


def test_cadrer_sans_trace_affichee(fenetre):
    dialogue = fenetre.ouvrir_impression()
    assert not dialogue.bouton_cadrer.isEnabled()
    assert dialogue.cadrer_sur_les_traces() is False


def test_mise_en_page_a_l_echelle():
    """La carte occupe exactement la taille prévue, le bandeau est dessiné."""
    px_par_mm = 4.0
    carte_mm = (100.0, 60.0)
    image = QImage(400, 240, QImage.Format.Format_RGB32)
    image.fill(QColor("#00ff00"))

    page = QImage(round(100 * px_par_mm), round(75 * px_par_mm), QImage.Format.Format_RGB32)
    page.fill(QColor("#ffffff"))
    painter = QPainter(page)
    cadre = peindre_page(
        painter, QRectF(0, 0, page.width(), page.height()), px_par_mm, image,
        carte_mm, 25000, titre="Essai", attribution="© test",
    )
    painter.end()

    assert cadre.width() == pytest.approx(100 * px_par_mm)
    assert cadre.height() == pytest.approx(60 * px_par_mm)
    assert page.pixelColor(200, 120) == QColor("#00ff00")
    # Le bandeau, sous la carte, porte du texte et la barre d'échelle.
    sombres = sum(
        1
        for y in range(round(cadre.bottom()) + 2, page.height())
        for x in range(page.width())
        if page.pixelColor(x, y).lightness() < 100
    )
    assert sombres > 200


def test_pdf_a_l_echelle(fenetre, trace_affichee, tmp_path):
    """De bout en bout : le PDF a le bon format, la carte la bonne échelle."""
    dialogue = fenetre.ouvrir_impression()
    dialogue.choix_orientation.setCurrentIndex(dialogue.choix_orientation.findData(PAYSAGE))
    dialogue.set_echelle(25000)
    fenetre.centre_carte = (48.921, 1.4405)

    chemin = dialogue.enregistrer_pdf(str(tmp_path / "carte.pdf"))

    assert chemin is not None
    contenu = (tmp_path / "carte.pdf").read_bytes()
    assert contenu.startswith(b"%PDF")

    document = QPdfDocument(None)
    document.load(chemin)
    assert document.pageCount() == 1
    taille = document.pagePointSize(0)
    # A4 paysage : 297 × 210 mm, soit 842 × 595 points.
    assert taille.width() == pytest.approx(297 / 25.4 * 72, abs=1)
    assert taille.height() == pytest.approx(210 / 25.4 * 72, abs=1)

    # L'échelle, mesurée dans la carte qui a servi au rendu : la largeur
    # rendue doit couvrir 277 mm × 25 000 = 6 925 m au sol.
    vue = dialogue._rendu.vue
    largeur_m = run_js_sync(
        vue,
        "(function () { var s = map.getSize(), y = s.y / 2;"
        " return map.distance(map.containerPointToLatLng([0, y]),"
        " map.containerPointToLatLng([s.x, y])); })()",
    )
    assert largeur_m == pytest.approx(6925, rel=0.005)
    # La carte rendue est bien centrée là où le cadre était montré.
    centre = run_js_sync(vue, "[map.getCenter().lat, map.getCenter().lng]")
    assert centre == pytest.approx([48.921, 1.4405], abs=1e-5)
    # Et la trace affichée y figure.
    assert run_js_sync(vue, f"geocairn.isTrackShown({trace_affichee})") is True
    # La carte est rendue sans boutons ni bandeau d'état.
    assert run_js_sync(
        vue, "document.body.classList.contains('impression')"
    ) is True
    assert fenetre.status_label.text().startswith("Carte enregistrée")


def test_un_second_pdf_reprend_l_image_en_cache(fenetre, tmp_path, monkeypatch):
    dialogue = fenetre.ouvrir_impression()
    # La carte se recadre sur la feuille à l'ouverture : on la laisse finir,
    # son nouveau centre remonte ensuite de Leaflet.
    wait_for(lambda: False, 1000)
    assert dialogue.enregistrer_pdf(str(tmp_path / "a.pdf"))

    rendus = []
    original = dialogue._rendu.rendre
    monkeypatch.setattr(
        dialogue._rendu, "rendre", lambda *a, **k: rendus.append(1) or original(*a, **k)
    )
    assert dialogue.enregistrer_pdf(str(tmp_path / "b.pdf"))
    assert rendus == [], "rien n'a changé : inutile de recharger la carte"

    # Déplacer la carte, en revanche, impose un nouveau rendu.
    fenetre.centre_carte = (48.94, 1.45)
    assert dialogue.enregistrer_pdf(str(tmp_path / "c.pdf"))
    assert rendus == [1]


def test_fermer_la_fenetre_ferme_la_carte_invisible(db, qapp, tmp_path):
    """Régression : la carte de rendu ne doit pas garder l'application ouverte."""
    window = MainWindow(db=db)
    window.show()
    assert wait_for(lambda: window.map_view.is_ready)
    dialogue = window.ouvrir_impression()
    window.centre_carte = (48.93, 1.44)
    assert dialogue.enregistrer_pdf(str(tmp_path / "carte.pdf"))
    vue = dialogue._rendu.vue

    window.close()
    qapp.processEvents()

    assert sip.isdeleted(vue) or not vue.isVisible()
    assert window.dialogue_impression is None
