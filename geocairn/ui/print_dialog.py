"""Impression de la carte : format de la feuille, échelle, aperçu, PDF.

Trois pièces :

- `RenduCarte` charge la carte dans une vue invisible, dimensionnée comme la
  feuille, et en prend l'image une fois les tuiles arrivées. Le zoom de
  Leaflet y est fractionnaire : c'est lui qui donne l'échelle exacte.
- `peindre_page` met la feuille en page : la carte, puis un bandeau portant le
  titre, l'échelle, une barre graduée, le nord et les sources.
- `DialogueImpression` réunit les réglages. Il n'est pas modal : un cadre
  pointillé, dessiné sur la carte principale, montre la zone imprimée, et l'on
  déplace la carte pour la choisir.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass

from PyQt6.QtCore import QEventLoop, QMarginsF, QObject, QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QImage,
    QPageLayout,
    QPageSize,
    QPainter,
    QPen,
    QPolygonF,
)
from PyQt6.QtPrintSupport import QPrintDialog, QPrinter, QPrintPreviewDialog
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QVBoxLayout,
)

from .. import APP_NAME
from ..impression import (
    ATTRIBUTIONS,
    BANDEAU_MM,
    ECHELLE_MAX,
    ECHELLE_MIN,
    ECHELLES,
    FORMATS,
    MARGE_MM,
    PAYSAGE,
    PORTRAIT,
    RESOLUTION_DPI,
    barre_echelle,
    echelle_pour_emprise,
    emprise_terrain,
    format_distance,
    format_echelle,
    format_emprise,
    lire_echelle,
    taille_pixels,
    zone_carte_format,
    zone_carte_mm,
    zoom_pour_echelle,
)
from .map_view import MapView

#: Correspondance entre nos formats et ceux que connaît Qt.
TAILLES_QT = {
    "A4": QPageSize.PageSizeId.A4,
    "A3": QPageSize.PageSizeId.A3,
    "A5": QPageSize.PageSizeId.A5,
    "Lettre US": QPageSize.PageSizeId.Letter,
}

LIBELLES_ORIENTATION = {PAYSAGE: "Paysage", PORTRAIT: "Portrait"}

#: Attente maximale de la carte invisible, puis de ses tuiles. Passé ce délai,
#: on imprime ce qui est arrivé plutôt que de ne rien imprimer du tout.
DELAI_CHARGEMENT_MS = 20000
DELAI_TUILES_MS = 45000

#: Les tuiles arrivées, Leaflet dessine encore les traces à l'image suivante.
DELAI_PEINTURE_MS = 400


def attendre(condition, delai_ms: int, abandon=lambda: False) -> bool:
    """Fait tourner la boucle Qt jusqu'à ce que `condition` soit vraie.

    Retourne la valeur finale de la condition. `abandon` permet à
    l'utilisateur d'interrompre l'attente (bouton d'une boîte de progression).
    """
    boucle = QEventLoop()
    minuteur = QTimer()
    ecoule = {"ms": 0}

    def tic() -> None:
        minuteur.stop()
        ecoule["ms"] += 50
        if condition() or abandon() or ecoule["ms"] >= delai_ms:
            boucle.quit()
        else:
            minuteur.start(50)

    minuteur.timeout.connect(tic)
    if condition():
        return True
    minuteur.start(50)
    boucle.exec()
    minuteur.stop()
    return condition()


# --------------------------------------------------------------------- rendu


class RenduCarte(QObject):
    """Carte invisible, à la taille de la feuille, dont on prend l'image."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        #: Vrai si le dernier rendu est parti sans toutes ses tuiles.
        self.incomplet = False
        # Une fenêtre à part, jamais montrée à l'écran : dimensionnée comme la
        # feuille, elle dépasse souvent la taille de l'écran.
        self.vue = MapView()
        self.vue.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        # Elle ne doit pas retenir l'application ouverte une fois la fenêtre
        # principale fermée.
        self.vue.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        self.vue.resize(800, 600)
        self.vue.show()

    def fermer(self) -> None:
        self.vue.close()
        self.vue.deleteLater()

    def _taille_carte(self) -> tuple[int, int] | None:
        """Taille que Leaflet attribue à la carte, après recalcul."""
        resultat = {}
        self.vue.page().runJavaScript(
            "geocairn.invalidateSize();",
            lambda valeur: resultat.setdefault("taille", valeur),
        )
        attendre(lambda: "taille" in resultat, 3000)
        taille = resultat.get("taille")
        return tuple(taille) if taille else None

    def rendre(
        self,
        lat: float,
        lon: float,
        zoom: float,
        largeur_px: int,
        hauteur_px: int,
        couche: str,
        traces,
        abandon=lambda: False,
    ) -> QImage | None:
        """Image de la carte centrée sur (lat, lon), ou None si abandon."""
        if not attendre(lambda: self.vue.is_ready, DELAI_CHARGEMENT_MS, abandon):
            return None

        # Chromium applique la nouvelle taille de façon différée : sans cette
        # attente, Leaflet cadrerait encore sur l'ancienne.
        self.vue.resize(largeur_px, hauteur_px)
        attendre(
            lambda: self._taille_carte() == (largeur_px, hauteur_px),
            DELAI_CHARGEMENT_MS,
            abandon,
        )

        self.vue.clear_tracks()
        for trace in traces:
            self.vue.show_track(
                trace.id, trace.points, trace.color, trace.opacity, name=trace.name
            )

        prete = {"ok": False}

        def signaler() -> None:
            prete["ok"] = True

        self.vue.impression_prete.connect(signaler)
        try:
            self.vue.preparer_impression(lat, lon, zoom, couche)
            complet = attendre(lambda: prete["ok"], DELAI_TUILES_MS, abandon)
        finally:
            self.vue.impression_prete.disconnect(signaler)
        if abandon():
            return None
        attendre(lambda: False, DELAI_PEINTURE_MS)

        self.incomplet = not complet
        return self.vue.grab().toImage()


# ------------------------------------------------------------- mise en page


def _police(taille_px: float, gras: bool = False) -> QFont:
    police = QFont("Segoe UI")
    police.setPixelSize(max(1, round(taille_px)))
    police.setBold(gras)
    return police


def peindre_page(
    painter: QPainter,
    zone: QRectF,
    px_par_mm: float,
    image: QImage,
    carte_mm: tuple[float, float],
    echelle: int,
    titre: str = "",
    attribution: str = "",
    date: datetime.date | None = None,
) -> QRectF:
    """Dessine la feuille dans `zone` (unités du périphérique).

    La carte occupe exactement `carte_mm` millimètres : c'est ce qui garantit
    l'échelle, quelle que soit la résolution de l'imprimante. Retourne le
    rectangle occupé par la carte.
    """
    mm = px_par_mm
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    cadre = QRectF(zone.left(), zone.top(), carte_mm[0] * mm, carte_mm[1] * mm)
    painter.drawImage(cadre, image, QRectF(image.rect()))
    painter.setPen(QPen(QColor("#000000"), 0.3 * mm))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRect(cadre)

    haut = cadre.bottom() + 2.5 * mm
    encre = QColor("#222222")
    gris = QColor("#555555")

    # À gauche : le titre, puis l'origine et la date.
    painter.setPen(encre)
    painter.setFont(_police(3.6 * mm, gras=True))
    gauche = QRectF(cadre.left(), haut, cadre.width() * 0.4, 5 * mm)
    painter.drawText(
        gauche,
        int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop),
        painter.fontMetrics().elidedText(
            titre or "Carte", Qt.TextElideMode.ElideRight, int(gauche.width())
        ),
    )
    date = date or datetime.date.today()
    painter.setPen(gris)
    painter.setFont(_police(2.6 * mm))
    painter.drawText(
        QRectF(cadre.left(), haut + 5 * mm, cadre.width() * 0.4, 4 * mm),
        int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop),
        f"{APP_NAME} — imprimé le {date.strftime('%d/%m/%Y')}",
    )

    # Au centre : l'échelle, en toutes lettres puis en barre graduée.
    centre_x = cadre.center().x()
    painter.setPen(encre)
    painter.setFont(_police(3.0 * mm, gras=True))
    painter.drawText(
        QRectF(centre_x - 30 * mm, haut - 0.5 * mm, 60 * mm, 4.5 * mm),
        int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop),
        f"Échelle {format_echelle(echelle)}",
    )
    metres, longueur_mm = barre_echelle(echelle, min(50.0, carte_mm[0] * 0.3))
    barre = QRectF(
        centre_x - longueur_mm * mm / 2, haut + 4.8 * mm, longueur_mm * mm, 1.6 * mm
    )
    moitie = QRectF(barre.left(), barre.top(), barre.width() / 2, barre.height())
    painter.setPen(QPen(encre, 0.2 * mm))
    painter.setBrush(QBrush(encre))
    painter.drawRect(moitie)
    painter.setBrush(QBrush(QColor("#ffffff")))
    painter.drawRect(moitie.translated(moitie.width(), 0))
    painter.setFont(_police(2.4 * mm))
    for x, texte in ((barre.left(), "0"), (barre.right(), format_distance(metres))):
        painter.drawText(
            QRectF(x - 15 * mm, barre.bottom() + 0.3 * mm, 30 * mm, 3.5 * mm),
            int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop),
            texte,
        )

    # À droite : le nord, puis les sources du fond de carte.
    fleche_x = cadre.right() - 3 * mm
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(encre))
    painter.drawPolygon(
        QPolygonF(
            [
                QPointF(fleche_x, haut),
                QPointF(fleche_x - 2 * mm, haut + 6 * mm),
                QPointF(fleche_x, haut + 4.8 * mm),
                QPointF(fleche_x + 2 * mm, haut + 6 * mm),
            ]
        )
    )
    painter.setPen(encre)
    painter.setFont(_police(2.6 * mm, gras=True))
    painter.drawText(
        QRectF(fleche_x - 3 * mm, haut + 6.2 * mm, 6 * mm, 3.5 * mm),
        int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop),
        "N",
    )
    if attribution:
        painter.setPen(gris)
        painter.setFont(_police(2.4 * mm))
        painter.drawText(
            QRectF(centre_x + 32 * mm, haut + 5 * mm,
                   fleche_x - 5 * mm - (centre_x + 32 * mm), 4 * mm),
            int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop),
            attribution,
        )

    painter.restore()
    return cadre


# ------------------------------------------------------------------ réglages


@dataclass
class ReglagesImpression:
    format_papier: str = "A4"
    orientation: str = PAYSAGE
    echelle: int = 25000

    def zone_carte(self) -> tuple[float, float]:
        return zone_carte_format(self.format_papier, self.orientation)

    def emprise(self) -> tuple[float, float]:
        return emprise_terrain(*self.zone_carte(), self.echelle)

    def mise_en_page(self) -> QPageLayout:
        return QPageLayout(
            QPageSize(TAILLES_QT[self.format_papier]),
            QPageLayout.Orientation.Landscape
            if self.orientation == PAYSAGE
            else QPageLayout.Orientation.Portrait,
            QMarginsF(MARGE_MM, MARGE_MM, MARGE_MM, MARGE_MM),
            QPageLayout.Unit.Millimeter,
        )


# ------------------------------------------------------------------ dialogue


class DialogueImpression(QDialog):
    """Réglages de l'impression, avec le cadre de la feuille sur la carte.

    La fenêtre principale fournit le centre de la carte, le fond affiché, les
    traces visibles et la carte où dessiner le cadre.
    """

    def __init__(self, fenetre, reglages: ReglagesImpression, titre: str = "") -> None:
        super().__init__(fenetre)
        self.fenetre = fenetre
        self.setWindowTitle("Imprimer la carte")
        self.setModal(False)
        self._rendu: RenduCarte | None = None
        self._cache: tuple | None = None   # (clé, image)
        self._imprimante: QPrinter | None = None

        self.choix_format = QComboBox(self)
        self.choix_format.addItems(list(FORMATS))
        self.choix_orientation = QComboBox(self)
        for cle, libelle in LIBELLES_ORIENTATION.items():
            self.choix_orientation.addItem(libelle, cle)
        self.choix_echelle = QComboBox(self)
        self.choix_echelle.setEditable(True)
        self.choix_echelle.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.choix_echelle.addItems([format_echelle(e) for e in ECHELLES])
        self.champ_titre = QLineEdit(titre, self)
        self.champ_titre.setPlaceholderText("Imprimé sous la carte (facultatif)")

        self.libelle_emprise = QLabel(self)
        self.libelle_emprise.setWordWrap(True)
        aide = QLabel(
            "Le cadre rouge, sur la carte, montre la zone imprimée.\n"
            "Déplacez la carte pour choisir ce qui figurera sur la feuille.",
            self,
        )
        aide.setStyleSheet("color: #555555;")
        aide.setWordWrap(True)

        formulaire = QFormLayout()
        formulaire.addRow("Format du papier :", self.choix_format)
        formulaire.addRow("Orientation :", self.choix_orientation)
        formulaire.addRow("Échelle :", self.choix_echelle)
        formulaire.addRow("Titre :", self.champ_titre)
        formulaire.addRow("Sur le terrain :", self.libelle_emprise)

        self.bouton_cadrer = QPushButton("Cadrer sur les traces affichées", self)
        self.bouton_cadrer.setToolTip(
            "Centre la feuille sur les traces affichées et choisit la plus "
            "grande échelle où elles tiennent entières"
        )
        self.bouton_cadrer.clicked.connect(self.cadrer_sur_les_traces)

        self.bouton_apercu = QPushButton("Aperçu…", self)
        self.bouton_apercu.clicked.connect(lambda: self.apercu())
        self.bouton_pdf = QPushButton("Enregistrer en PDF…", self)
        self.bouton_pdf.clicked.connect(lambda: self.enregistrer_pdf())
        self.bouton_imprimer = QPushButton("Imprimer…", self)
        self.bouton_imprimer.setDefault(True)
        self.bouton_imprimer.clicked.connect(lambda: self.imprimer())
        fermer = QPushButton("Fermer", self)
        fermer.clicked.connect(self.close)

        boutons = QHBoxLayout()
        boutons.addWidget(self.bouton_apercu)
        boutons.addWidget(self.bouton_pdf)
        boutons.addStretch(1)
        boutons.addWidget(self.bouton_imprimer)
        boutons.addWidget(fermer)

        disposition = QVBoxLayout(self)
        disposition.addLayout(formulaire)
        disposition.addWidget(self.bouton_cadrer)
        disposition.addWidget(aide)
        disposition.addLayout(boutons)
        # Étroite, elle tient sur la bibliothèque sans déborder sur la carte.
        self.setMaximumWidth(460)

        self.appliquer_reglages(reglages)
        self.choix_format.currentIndexChanged.connect(lambda: self._mettre_a_jour())
        self.choix_orientation.currentIndexChanged.connect(
            lambda: self._mettre_a_jour()
        )
        self.choix_echelle.currentTextChanged.connect(lambda: self._mettre_a_jour())
        self._mettre_a_jour()

    # ------------------------------------------------------------ réglages

    def appliquer_reglages(self, reglages: ReglagesImpression) -> None:
        if reglages.format_papier in FORMATS:
            self.choix_format.setCurrentText(reglages.format_papier)
        index = self.choix_orientation.findData(reglages.orientation)
        if index >= 0:
            self.choix_orientation.setCurrentIndex(index)
        self.set_echelle(reglages.echelle)

    def set_echelle(self, echelle: int) -> None:
        self.choix_echelle.setCurrentText(format_echelle(echelle))

    def echelle(self) -> int | None:
        return lire_echelle(self.choix_echelle.currentText())

    def reglages(self) -> ReglagesImpression | None:
        """Réglages saisis, ou None si l'échelle n'est pas lisible."""
        echelle = self.echelle()
        if echelle is None:
            return None
        return ReglagesImpression(
            self.choix_format.currentText(),
            self.choix_orientation.currentData(),
            echelle,
        )

    def _mettre_a_jour(
        self, ajuster: bool = True, centre: tuple[float, float] | None = None
    ) -> None:
        """Répercute les réglages sur l'emprise affichée et le cadre."""
        reglages = self.reglages()
        valide = reglages is not None
        for bouton in (self.bouton_apercu, self.bouton_pdf, self.bouton_imprimer):
            bouton.setEnabled(valide)
        self.bouton_cadrer.setEnabled(bool(self.fenetre.visible_tracks))

        if not valide:
            self.libelle_emprise.setStyleSheet("color: #c62828;")
            self.libelle_emprise.setText(
                f"échelle illisible : saisissez un nombre entre "
                f"{format_echelle(ECHELLE_MIN)} et {format_echelle(ECHELLE_MAX)}"
            )
            self.fenetre.map_view.clear_print_frame()
            return

        largeur, hauteur = reglages.emprise()
        self.libelle_emprise.setStyleSheet("")
        self.libelle_emprise.setText(format_emprise(largeur, hauteur))
        self.fenetre.map_view.set_print_frame(largeur, hauteur, ajuster, centre)

    def cadrer_sur_les_traces(self) -> bool:
        """Centre la feuille sur les traces affichées, à l'échelle qui convient.

        L'orientation suit la forme des traces : une randonnée qui file du
        nord au sud tient souvent en portrait à une échelle plus détaillée.
        À échelle égale, l'orientation choisie par l'utilisateur est gardée.
        """
        emprise = self.fenetre.emprise_traces_affichees()
        if emprise is None:
            return False
        lat, lon, largeur_m, hauteur_m = emprise

        format_papier = self.choix_format.currentText()
        actuelle = self.choix_orientation.currentData()
        candidates = [actuelle] + [o for o in (PAYSAGE, PORTRAIT) if o != actuelle]
        echelle, orientation = min(
            (
                echelle_pour_emprise(
                    largeur_m, hauteur_m, *zone_carte_format(format_papier, o)
                ),
                rang,
            )
            for rang, o in enumerate(candidates)
        )
        orientation = candidates[orientation]

        self.fenetre.centre_carte = (lat, lon)
        for champ in (self.choix_orientation, self.choix_echelle):
            champ.blockSignals(True)
        self.choix_orientation.setCurrentIndex(
            self.choix_orientation.findData(orientation)
        )
        self.set_echelle(echelle)
        for champ in (self.choix_orientation, self.choix_echelle):
            champ.blockSignals(False)
        self._mettre_a_jour(centre=(lat, lon))
        return True

    # --------------------------------------------------------------- rendu

    def _image(self, reglages: ReglagesImpression, carte_mm) -> QImage | None:
        """Image de la carte pour une zone de `carte_mm`, rendue au besoin."""
        lat, lon = self.fenetre.centre_carte
        couche = self.fenetre.fond_de_carte
        traces = self.fenetre.traces_pour_impression()
        cle = (
            round(carte_mm[0], 2), round(carte_mm[1], 2), reglages.echelle,
            round(lat, 7), round(lon, 7), couche,
            tuple((t.id, t.color, t.opacity, t.point_count) for t in traces),
        )
        if self._cache is not None and self._cache[0] == cle:
            return self._cache[1]

        attente = QProgressDialog(
            "Préparation de la carte à imprimer…", "Interrompre", 0, 0, self
        )
        attente.setWindowTitle("Impression")
        attente.setWindowModality(Qt.WindowModality.ApplicationModal)
        attente.setMinimumDuration(0)
        attente.show()
        try:
            if self._rendu is None:
                self._rendu = RenduCarte(self)
            largeur_px, hauteur_px = taille_pixels(*carte_mm)
            image = self._rendu.rendre(
                lat, lon,
                zoom_pour_echelle(reglages.echelle, lat, RESOLUTION_DPI),
                largeur_px, hauteur_px, couche, traces,
                abandon=attente.wasCanceled,
            )
        finally:
            attente.close()

        if image is None or image.isNull():
            return None
        if self._rendu.incomplet:
            self.fenetre.status_label.setText(
                "Impression : certaines tuiles de la carte ne sont pas arrivées "
                "à temps (connexion à Internet ?)."
            )
        self._cache = (cle, image)
        return image

    def dessiner_sur(self, imprimante: QPrinter) -> bool:
        """Met la feuille en page sur une imprimante (ou un PDF, un aperçu).

        La zone de la carte se déduit de la feuille réellement choisie : si
        l'utilisateur change de papier dans la boîte de Windows, l'échelle
        reste juste, seule l'étendue couverte change.
        """
        reglages = self.reglages()
        if reglages is None:
            return False
        utile = imprimante.pageLayout().paintRect(QPageLayout.Unit.Millimeter)
        carte_mm = zone_carte_mm(utile.width(), utile.height(), BANDEAU_MM)
        image = self._image(reglages, carte_mm)
        if image is None:
            return False

        painter = QPainter()
        if not painter.begin(imprimante):
            return False
        px_par_mm = imprimante.resolution() / 25.4
        zone = QRectF(0, 0, utile.width() * px_par_mm, utile.height() * px_par_mm)
        peindre_page(
            painter, zone, px_par_mm, image, carte_mm, reglages.echelle,
            titre=self.champ_titre.text().strip(),
            attribution=ATTRIBUTIONS.get(self.fenetre.fond_de_carte, ""),
        )
        painter.end()
        return True

    def _preparer(self, imprimante: QPrinter) -> bool:
        reglages = self.reglages()
        if reglages is None:
            return False
        imprimante.setPageLayout(reglages.mise_en_page())
        return True

    def apercu(self) -> bool:
        """Aperçu avant impression ; on peut imprimer depuis cette fenêtre."""
        imprimante = self._imprimante_partagee()
        if not self._preparer(imprimante):
            return False
        fenetre = QPrintPreviewDialog(imprimante, self)
        fenetre.setWindowTitle("Aperçu avant impression")
        fenetre.paintRequested.connect(self.dessiner_sur)
        fenetre.resize(1000, 760)
        fenetre.exec()
        return True

    def imprimer(self) -> bool:
        imprimante = self._imprimante_partagee()
        if not self._preparer(imprimante):
            return False
        boite = QPrintDialog(imprimante, self)
        boite.setWindowTitle("Imprimer la carte")
        if boite.exec() != QDialog.DialogCode.Accepted:
            return False
        if not self.dessiner_sur(imprimante):
            QMessageBox.warning(self, "Impression", "La carte n'a pas pu être imprimée.")
            return False
        self.fenetre.status_label.setText("Carte envoyée à l'imprimante.")
        return True

    def enregistrer_pdf(self, chemin: str | None = None) -> str | None:
        """Écrit la feuille dans un fichier PDF.

        `chemin` sert aux tests ; sans lui, l'emplacement est demandé.
        """
        demande = chemin is None
        if demande:
            nom = self.champ_titre.text().strip() or "Carte"
            chemin, _filtre = QFileDialog.getSaveFileName(
                self,
                "Enregistrer la carte en PDF",
                self.fenetre._chemin_export_propose(nom, ".pdf"),
                "Documents PDF (*.pdf)",
            )
            if not chemin:
                return None

        imprimante = QPrinter(QPrinter.PrinterMode.HighResolution)
        imprimante.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        imprimante.setOutputFileName(chemin)
        imprimante.setCreator(APP_NAME)
        imprimante.setDocName(self.champ_titre.text().strip() or "Carte")
        if not self._preparer(imprimante) or not self.dessiner_sur(imprimante):
            QMessageBox.warning(self, "Impression", "Le PDF n'a pas pu être écrit.")
            return None

        if demande:
            self.fenetre.retenir_dossier_export(chemin)
        self.fenetre.status_label.setText(f"Carte enregistrée dans {chemin}.")
        return chemin

    def _imprimante_partagee(self) -> QPrinter:
        """Une imprimante pour toute la séance : son choix est retenu."""
        if self._imprimante is None:
            self._imprimante = QPrinter(QPrinter.PrinterMode.HighResolution)
            self._imprimante.setDocName(self.champ_titre.text().strip() or "Carte")
        return self._imprimante

    # ------------------------------------------------------------ fermeture

    def done(self, code: int) -> None:
        # Fermer, Échap ou la croix passent tous par ici.
        self.liberer()
        super().done(code)

    def closeEvent(self, event):  # noqa: N802
        self.liberer()
        super().closeEvent(event)

    def liberer(self) -> None:
        """Retire le cadre de la carte et ferme la carte invisible."""
        self.fenetre.map_view.clear_print_frame()
        if self._rendu is not None:
            self._rendu.fermer()
            self._rendu = None
        self._cache = None
