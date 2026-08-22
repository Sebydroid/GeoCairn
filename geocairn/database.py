"""Accès à la base SQLite locale (dossiers, traces, points GPS)."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable, Sequence

from .config import db_path
from .models import (
    DEFAULT_TRACK_COLOR,
    DEFAULT_TRACK_OPACITY,
    Folder,
    Point,
    Track,
)
from .simplify import simplify_to

SCHEMA_VERSION = 5

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS folders (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL,
    parent_id  INTEGER REFERENCES folders(id) ON DELETE CASCADE,
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Unicité du nom au sein d'un même parent. IFNULL car SQLite considère les
-- NULL comme distincts dans un index unique (racine = parent_id NULL).
CREATE UNIQUE INDEX IF NOT EXISTS idx_folders_unique
    ON folders(IFNULL(parent_id, -1), name);

CREATE TABLE IF NOT EXISTS tracks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    folder_id   INTEGER REFERENCES folders(id) ON DELETE CASCADE,
    color       TEXT    NOT NULL DEFAULT '#1f5fbf',
    opacity     REAL    NOT NULL DEFAULT 0.9,
    description TEXT    NOT NULL DEFAULT '',
    is_loop     INTEGER NOT NULL DEFAULT 0,
    visible     INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_tracks_folder ON tracks(folder_id);

CREATE TABLE IF NOT EXISTS points (
    track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    seq      INTEGER NOT NULL,
    lat      REAL    NOT NULL,
    lon      REAL    NOT NULL,
    ele      REAL,
    time     TEXT,
    ele_service REAL,
    PRIMARY KEY (track_id, seq)
) WITHOUT ROWID;
"""


#: Suffixe des copies, pour qu'on ne confonde pas l'original et son double.
SUFFIXE_COPIE = "-copie"

#: Suffixe des traces décimées.
SUFFIXE_DECIME = "-décimé"


def _nom_libre(base: str, pris: set[str]) -> str:
    """`base` si elle est libre, sinon « base 2 », « base 3 »…"""
    if base not in pris:
        return base
    rang = 2
    while f"{base} {rang}" in pris:
        rang += 1
    return f"{base} {rang}"


class DuplicateNameError(ValueError):
    """Un dossier du même nom existe déjà au même niveau."""


class NotFoundError(LookupError):
    """L'élément demandé n'existe pas."""


class CycleError(ValueError):
    """Le déplacement demandé rendrait un dossier descendant de lui-même."""


class FutureSchemaError(RuntimeError):
    """La base a été écrite par une version plus récente du logiciel.

    Cas d'un retour en arrière : l'utilisateur réinstalle une version
    antérieure par-dessus la dernière. Les migrations ne savent qu'avancer ;
    poursuivre reviendrait à laisser du code d'hier écrire dans un schéma
    d'aujourd'hui, et à abîmer les traces sans prévenir.
    """

    def __init__(self, trouvee: int, connue: int) -> None:
        super().__init__(
            f"base en version {trouvee}, ce logiciel ne connaît que la {connue}"
        )
        self.trouvee = trouvee
        self.connue = connue


class Database:
    """Couche d'accès aux données.

    Utilisable comme gestionnaire de contexte :
        with Database() as db: ...
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else db_path()
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._closed = False
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        try:
            self._create_schema()
        except BaseException:
            # Une ouverture refusée ne doit pas laisser le fichier retenu :
            # sous Windows, il resterait verrouillé jusqu'à la fin du
            # programme, et l'utilisateur ne pourrait ni le déplacer ni le
            # restaurer d'une sauvegarde.
            self._closed = True
            self.conn.close()
            raise

    # ------------------------------------------------------------------ base

    def _create_schema(self) -> None:
        with self.conn:
            self.conn.executescript(SCHEMA)
            row = self.conn.execute(
                "SELECT value FROM meta WHERE key = 'schema_version'"
            ).fetchone()
            if row is None:
                self.conn.execute(
                    "INSERT INTO meta(key, value) VALUES ('schema_version', ?)",
                    (str(SCHEMA_VERSION),),
                )
            else:
                self._migrate(int(row["value"]))

            # L'unicité des noms de traces est posée après coup : une base
            # existante peut contenir des doublons, qu'il faut départager avant
            # que l'index ne les refuse.
            self._dedupe_track_names()
            self.conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_tracks_unique"
                " ON tracks(IFNULL(folder_id, -1), name)"
            )

            # Une écriture pour de bon, dès l'ouverture. Sur une base déjà en
            # place, tout ce qui précède se contente de lire : un fichier en
            # lecture seule (restauré d'une sauvegarde, posé sur un support
            # protégé) passait alors inaperçu jusqu'à la première trace
            # enregistrée, où le refus d'écriture emportait l'application.
            self.conn.execute(
                "INSERT INTO meta(key, value) VALUES ('derniere_ouverture',"
                " datetime('now'))"
                " ON CONFLICT(key) DO UPDATE SET value = excluded.value"
            )

    def _dedupe_track_names(self) -> int:
        """Renomme les traces homonymes d'un même dossier. Retourne le nombre."""
        doublons = self.conn.execute(
            "SELECT folder_id, name FROM tracks"
            " GROUP BY IFNULL(folder_id, -1), name HAVING COUNT(*) > 1"
        ).fetchall()

        renommees = 0
        for ligne in doublons:
            rangs = self.conn.execute(
                "SELECT id FROM tracks WHERE folder_id IS ? AND name = ?"
                " ORDER BY id",
                (ligne["folder_id"], ligne["name"]),
            ).fetchall()
            pris = {
                r["name"]
                for r in self.conn.execute(
                    "SELECT name FROM tracks WHERE folder_id IS ?",
                    (ligne["folder_id"],),
                )
            }
            for rang in rangs[1:]:   # la première garde son nom
                nouveau = _nom_libre(ligne["name"], pris)
                pris.add(nouveau)
                self.conn.execute(
                    "UPDATE tracks SET name = ? WHERE id = ?",
                    (nouveau, rang["id"]),
                )
                renommees += 1
        return renommees

    def unique_track_name(
        self, folder_id: int | None, base: str, sauf: int | None = None
    ) -> str:
        """Nom de trace libre dans ce dossier, en suffixant si besoin."""
        pris = {
            t.name for t in self.list_tracks(folder_id) if t.id != sauf
        }
        return _nom_libre(base, pris)

    def _migrate(self, version: int) -> None:
        """Met à niveau une base existante sans toucher aux données.

        `CREATE TABLE IF NOT EXISTS` n'ajoute pas les colonnes apparues après
        coup : il faut les poser explicitement.
        """
        if version > SCHEMA_VERSION:
            raise FutureSchemaError(version, SCHEMA_VERSION)
        if version == SCHEMA_VERSION:
            return

        colonnes = {
            r["name"] for r in self.conn.execute("PRAGMA table_info(tracks)")
        }
        if version < 2 and "opacity" not in colonnes:
            self.conn.execute(
                "ALTER TABLE tracks ADD COLUMN opacity REAL NOT NULL DEFAULT 0.9"
            )
        if version < 3 and "visible" not in colonnes:
            self.conn.execute(
                "ALTER TABLE tracks ADD COLUMN visible INTEGER NOT NULL DEFAULT 0"
            )
        if version < 4:
            colonnes_points = {
                r["name"] for r in self.conn.execute("PRAGMA table_info(points)")
            }
            if "ele_service" not in colonnes_points:
                self.conn.execute("ALTER TABLE points ADD COLUMN ele_service REAL")

        self.conn.execute(
            "UPDATE meta SET value = ? WHERE key = 'schema_version'",
            (str(SCHEMA_VERSION),),
        )

    @property
    def schema_version(self) -> int:
        row = self.conn.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        ).fetchone()
        return int(row["value"]) if row else 0

    # ------------------------------------------------------------- réglages

    def get_meta(self, cle: str, defaut: str = "") -> str:
        """Valeur d'un réglage rangé dans la table `meta`.

        La table existe depuis l'origine pour la version du schéma ; elle sert
        aussi aux quelques réglages qui suivent la bibliothèque de l'utilisateur
        plutôt que la machine — la version de mise à jour écartée, par exemple.
        """
        ligne = self.conn.execute(
            "SELECT value FROM meta WHERE key = ?", (cle,)
        ).fetchone()
        return ligne["value"] if ligne else defaut

    def set_meta(self, cle: str, valeur: str) -> None:
        """Écrit un réglage dans la table `meta`."""
        with self.conn:
            self.conn.execute(
                "INSERT INTO meta(key, value) VALUES (?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (cle, str(valeur)),
            )

    def close(self) -> None:
        self._closed = True
        self.conn.close()

    @property
    def closed(self) -> bool:
        """Vrai une fois la connexion fermée.

        Permet à l'interface de ne pas interroger une base close depuis un
        traitement différé : l'exception surviendrait dans un slot Qt, ce qui
        interromprait tout le programme.
        """
        return self._closed

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    # --------------------------------------------------------------- dossiers

    def create_folder(self, name: str, parent_id: int | None = None) -> int:
        """Crée un dossier. Lève DuplicateNameError si le nom est déjà pris."""
        name = name.strip()
        if not name:
            raise ValueError("Le nom du dossier ne peut pas être vide.")
        if parent_id is not None and self.get_folder(parent_id) is None:
            raise NotFoundError(f"Dossier parent {parent_id} introuvable.")
        try:
            with self.conn:
                cur = self.conn.execute(
                    "INSERT INTO folders(name, parent_id) VALUES (?, ?)",
                    (name, parent_id),
                )
        except sqlite3.IntegrityError as exc:
            raise DuplicateNameError(
                f"Un dossier nommé « {name} » existe déjà à cet emplacement."
            ) from exc
        return int(cur.lastrowid)

    def get_folder(self, folder_id: int) -> Folder | None:
        row = self.conn.execute(
            "SELECT id, name, parent_id FROM folders WHERE id = ?", (folder_id,)
        ).fetchone()
        return Folder(row["id"], row["name"], row["parent_id"]) if row else None

    def list_folders(self, parent_id: int | None = None) -> list[Folder]:
        """Sous-dossiers directs de `parent_id` (racine si None), triés par nom."""
        if parent_id is None:
            rows = self.conn.execute(
                "SELECT id, name, parent_id FROM folders WHERE parent_id IS NULL"
                " ORDER BY name COLLATE NOCASE"
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT id, name, parent_id FROM folders WHERE parent_id = ?"
                " ORDER BY name COLLATE NOCASE",
                (parent_id,),
            ).fetchall()
        return [Folder(r["id"], r["name"], r["parent_id"]) for r in rows]

    def rename_folder(self, folder_id: int, name: str) -> None:
        name = name.strip()
        if not name:
            raise ValueError("Le nom du dossier ne peut pas être vide.")
        if self.get_folder(folder_id) is None:
            raise NotFoundError(f"Dossier {folder_id} introuvable.")
        try:
            with self.conn:
                self.conn.execute(
                    "UPDATE folders SET name = ? WHERE id = ?", (name, folder_id)
                )
        except sqlite3.IntegrityError as exc:
            raise DuplicateNameError(
                f"Un dossier nommé « {name} » existe déjà à cet emplacement."
            ) from exc

    def delete_folder(self, folder_id: int) -> None:
        """Supprime un dossier, ses sous-dossiers et leurs traces (cascade)."""
        with self.conn:
            self.conn.execute("DELETE FROM folders WHERE id = ?", (folder_id,))

    def folder_ancestors(self, folder_id: int) -> list[int]:
        """Identifiants des dossiers parents, du plus proche à la racine."""
        ancestors: list[int] = []
        current = self.get_folder(folder_id)
        while current is not None and current.parent_id is not None:
            ancestors.append(current.parent_id)
            current = self.get_folder(current.parent_id)
        return ancestors

    def move_folder(self, folder_id: int, parent_id: int | None) -> None:
        """Déplace un dossier sous un autre parent (glisser-déposer).

        Refuse de créer un cycle : un dossier ne peut pas devenir son propre
        descendant, sans quoi la branche disparaîtrait de l'arborescence.
        """
        if self.get_folder(folder_id) is None:
            raise NotFoundError(f"Dossier {folder_id} introuvable.")
        if parent_id is not None:
            if self.get_folder(parent_id) is None:
                raise NotFoundError(f"Dossier {parent_id} introuvable.")
            if parent_id == folder_id:
                raise CycleError("Un dossier ne peut pas être placé dans lui-même.")
            if folder_id in self.folder_ancestors(parent_id):
                raise CycleError(
                    "Un dossier ne peut pas être placé dans l'un de ses "
                    "sous-dossiers."
                )
        try:
            with self.conn:
                self.conn.execute(
                    "UPDATE folders SET parent_id = ? WHERE id = ?",
                    (parent_id, folder_id),
                )
        except sqlite3.IntegrityError as exc:
            name = self.get_folder(folder_id).name
            raise DuplicateNameError(
                f"Un dossier nommé « {name} » existe déjà à cet emplacement."
            ) from exc

    # ----------------------------------------------------------------- traces

    def create_track(
        self,
        name: str,
        folder_id: int | None = None,
        points: Sequence[Point] | None = None,
        color: str = DEFAULT_TRACK_COLOR,
        description: str = "",
        is_loop: bool = False,
        opacity: float = DEFAULT_TRACK_OPACITY,
    ) -> int:
        name = name.strip() or "Trace sans nom"
        if folder_id is not None and self.get_folder(folder_id) is None:
            raise NotFoundError(f"Dossier {folder_id} introuvable.")
        # Deux traces homonymes dans un même dossier ne se distingueraient plus
        # dans l'arborescence : la nouvelle venue prend un suffixe.
        name = self.unique_track_name(folder_id, name)
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO tracks(name, folder_id, color, opacity, description,"
                " is_loop) VALUES (?, ?, ?, ?, ?, ?)",
                (name, folder_id, color, opacity, description, int(is_loop)),
            )
            track_id = int(cur.lastrowid)
            if points:
                self._insert_points(track_id, points, start_seq=0)
        return track_id

    def get_track(self, track_id: int, with_points: bool = False) -> Track | None:
        row = self.conn.execute(
            "SELECT t.*, (SELECT COUNT(*) FROM points p WHERE p.track_id = t.id)"
            " AS point_count FROM tracks t WHERE t.id = ?",
            (track_id,),
        ).fetchone()
        if row is None:
            return None
        track = Track(
            id=row["id"],
            name=row["name"],
            folder_id=row["folder_id"],
            color=row["color"],
            opacity=row["opacity"],
            description=row["description"],
            is_loop=bool(row["is_loop"]),
            visible=bool(row["visible"]),
            point_count=row["point_count"],
        )
        if with_points:
            track.points = self.get_points(track_id)
        return track

    def list_tracks(self, folder_id: int | None = None) -> list[Track]:
        sql = (
            "SELECT t.*, (SELECT COUNT(*) FROM points p WHERE p.track_id = t.id)"
            " AS point_count FROM tracks t WHERE t.folder_id IS ?"
            " ORDER BY t.name COLLATE NOCASE"
        )
        rows = self.conn.execute(sql, (folder_id,)).fetchall()
        return [
            Track(
                id=r["id"],
                name=r["name"],
                folder_id=r["folder_id"],
                color=r["color"],
                opacity=r["opacity"],
                description=r["description"],
                is_loop=bool(r["is_loop"]),
                point_count=r["point_count"],
            )
            for r in rows
        ]

    def rename_track(self, track_id: int, name: str) -> None:
        name = name.strip()
        if not name:
            raise ValueError("Le nom de la trace ne peut pas être vide.")
        track = self.get_track(track_id)
        if track is None:
            raise NotFoundError(f"Trace {track_id} introuvable.")
        # Renommage demandé par l'utilisateur : on le prévient plutôt que de
        # suffixer dans son dos.
        if name != track.name and name in {
            t.name for t in self.list_tracks(track.folder_id) if t.id != track_id
        }:
            raise DuplicateNameError(
                f"Une trace nommée « {name} » existe déjà dans ce dossier."
            )
        with self.conn:
            self.conn.execute(
                "UPDATE tracks SET name = ?, updated_at = datetime('now')"
                " WHERE id = ?",
                (name, track_id),
            )

    def set_track_loop(self, track_id: int, is_loop: bool) -> None:
        """Mémorise si la trace forme une boucle."""
        with self.conn:
            self.conn.execute(
                "UPDATE tracks SET is_loop = ?, updated_at = datetime('now')"
                " WHERE id = ?",
                (int(bool(is_loop)), track_id),
            )

    def set_track_visible(self, track_id: int, visible: bool) -> None:
        """Mémorise si la trace doit être affichée à la réouverture."""
        with self.conn:
            self.conn.execute(
                "UPDATE tracks SET visible = ? WHERE id = ?",
                (int(bool(visible)), track_id),
            )

    def visible_track_ids(self) -> list[int]:
        """Traces à réafficher au lancement."""
        return [
            row["id"]
            for row in self.conn.execute(
                "SELECT id FROM tracks WHERE visible = 1 ORDER BY id"
            )
        ]

    def set_track_style(
        self,
        track_id: int,
        color: str | None = None,
        opacity: float | None = None,
    ) -> None:
        """Change la couleur et/ou la transparence d'une trace."""
        if self.get_track(track_id) is None:
            raise NotFoundError(f"Trace {track_id} introuvable.")
        if opacity is not None:
            opacity = max(0.05, min(1.0, float(opacity)))
        with self.conn:
            if color is not None:
                self.conn.execute(
                    "UPDATE tracks SET color = ? WHERE id = ?", (color, track_id)
                )
            if opacity is not None:
                self.conn.execute(
                    "UPDATE tracks SET opacity = ? WHERE id = ?", (opacity, track_id)
                )
            self._touch(track_id)

    def move_track(self, track_id: int, folder_id: int | None) -> None:
        if folder_id is not None and self.get_folder(folder_id) is None:
            raise NotFoundError(f"Dossier {folder_id} introuvable.")
        track = self.get_track(track_id)
        if track is None:
            raise NotFoundError(f"Trace {track_id} introuvable.")
        # Un nom déjà pris à l'arrivée ne doit pas empêcher le déplacement.
        nom = self.unique_track_name(folder_id, track.name, sauf=track_id)
        with self.conn:
            self.conn.execute(
                "UPDATE tracks SET folder_id = ?, name = ?,"
                " updated_at = datetime('now') WHERE id = ?",
                (folder_id, nom, track_id),
            )

    def delete_track(self, track_id: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM tracks WHERE id = ?", (track_id,))

    # ------------------------------------------------- duplication, découpage

    def unique_folder_name(self, parent_id: int | None, base: str) -> str:
        """Nom libre dans ce dossier, en suffixant si besoin."""
        return _nom_libre(base, {f.name for f in self.list_folders(parent_id)})

    def copy_track_name(self, track_id: int, folder_id: int | None) -> str:
        """Nom de la copie d'une trace : « Nom-copie », puis « Nom-copie 2 »."""
        track = self.get_track(track_id)
        if track is None:
            raise NotFoundError(f"Trace {track_id} introuvable.")
        pris = {t.name for t in self.list_tracks(folder_id)}
        return _nom_libre(f"{track.name}{SUFFIXE_COPIE}", pris)

    def copy_track_to(self, track_id: int, folder_id: int | None) -> int:
        """Copie une trace dans un dossier, en la suffixant « -copie »."""
        track = self.get_track(track_id, with_points=True)
        if track is None:
            raise NotFoundError(f"Trace {track_id} introuvable.")
        return self.create_track(
            self.copy_track_name(track_id, folder_id),
            folder_id=folder_id,
            points=track.points,
            color=track.color,
            opacity=track.opacity,
            description=track.description,
            is_loop=track.is_loop,
        )

    def copy_folder(
        self, folder_id: int, parent_id: int | None, name: str | None = None
    ) -> int:
        """Copie un dossier, ses sous-dossiers et toutes leurs traces.

        Le nom est adapté si l'emplacement d'arrivée en contient déjà un
        identique.
        """
        source = self.get_folder(folder_id)
        if source is None:
            raise NotFoundError(f"Dossier {folder_id} introuvable.")
        if parent_id is not None and (
            folder_id == parent_id or folder_id in self.folder_ancestors(parent_id)
        ):
            raise CycleError(
                "Un dossier ne peut pas être copié dans lui-même ni dans l'un "
                "de ses sous-dossiers."
            )

        nouveau = self.create_folder(
            self.unique_folder_name(parent_id, name or source.name), parent_id
        )
        for track in self.list_tracks(folder_id):
            points = self.get_points(track.id)
            self.create_track(
                track.name,
                folder_id=nouveau,
                points=points,
                color=track.color,
                opacity=track.opacity,
                description=track.description,
                is_loop=track.is_loop,
            )
        for sous in self.list_folders(folder_id):
            self.copy_folder(sous.id, nouveau)
        return nouveau

    def duplicate_track(self, track_id: int, name: str | None = None) -> int:
        """Copie une trace avec ses points, dans le même dossier."""
        track = self.get_track(track_id, with_points=True)
        if track is None:
            raise NotFoundError(f"Trace {track_id} introuvable.")
        return self.create_track(
            name
            if name is not None
            else self.copy_track_name(track_id, track.folder_id),
            folder_id=track.folder_id,
            points=track.points,
            color=track.color,
            opacity=track.opacity,
            description=track.description,
            is_loop=track.is_loop,
        )

    def decimate_track(self, track_id: int, cible: int) -> int | None:
        """Crée une copie allégée d'une trace, ramenée à `cible` points.

        L'original n'est pas touché. Retourne l'identifiant de la copie, ou None
        si la trace est déjà plus courte que demandé.
        """
        track = self.get_track(track_id, with_points=True)
        if track is None:
            raise NotFoundError(f"Trace {track_id} introuvable.")
        if cible >= len(track.points):
            return None

        allegee = simplify_to(track.points, cible)
        nom = _nom_libre(
            f"{track.name}{SUFFIXE_DECIME}",
            {t.name for t in self.list_tracks(track.folder_id)},
        )
        return self.create_track(
            nom,
            folder_id=track.folder_id,
            points=allegee,
            color=track.color,
            opacity=track.opacity,
            description=track.description,
            is_loop=track.is_loop,
        )

    def split_track(self, track_id: int, index: int) -> tuple[int, int]:
        """Découpe une trace en deux au point `index`.

        Le point de coupure appartient aux deux moitiés, afin qu'elles se
        touchent. La trace d'origine conserve son identifiant et devient la
        première moitié ; la seconde donne une nouvelle trace « (suite) ».
        Retourne les deux identifiants.
        """
        track = self.get_track(track_id, with_points=True)
        if track is None:
            raise NotFoundError(f"Trace {track_id} introuvable.")
        if not 1 <= index <= len(track.points) - 2:
            raise ValueError(
                "Le point de découpe doit laisser au moins deux points de "
                "chaque côté."
            )

        premiere = track.points[: index + 1]
        seconde = track.points[index:]

        second_id = self.create_track(
            f"{track.name} (suite)",
            folder_id=track.folder_id,
            points=seconde,
            color=track.color,
            opacity=track.opacity,
            description=track.description,
        )
        self.replace_points(track_id, premiere)
        with self.conn:
            self.conn.execute(
                "UPDATE tracks SET is_loop = 0 WHERE id = ?", (track_id,)
            )
        return (track_id, second_id)

    def merge_tracks(
        self,
        first_id: int,
        second_id: int,
        name: str | None = None,
        keep_sources: bool = False,
    ) -> int:
        """Fusionne deux traces en une nouvelle, dans l'ordre indiqué.

        Les deux traces d'origine sont supprimées, sauf si `keep_sources`.
        Retourne l'identifiant de la trace fusionnée.
        """
        if first_id == second_id:
            raise ValueError("Une trace ne peut pas être fusionnée avec elle-même.")
        first = self.get_track(first_id, with_points=True)
        second = self.get_track(second_id, with_points=True)
        if first is None:
            raise NotFoundError(f"Trace {first_id} introuvable.")
        if second is None:
            raise NotFoundError(f"Trace {second_id} introuvable.")

        merged_id = self.create_track(
            name if name is not None else f"{first.name} + {second.name}",
            folder_id=first.folder_id,
            points=first.points + second.points,
            color=first.color,
            opacity=first.opacity,
        )
        if not keep_sources:
            self.delete_track(first_id)
            self.delete_track(second_id)
        return merged_id

    # ----------------------------------------------------------------- points

    def _insert_points(
        self, track_id: int, points: Iterable[Point], start_seq: int
    ) -> None:
        self.conn.executemany(
            "INSERT INTO points(track_id, seq, lat, lon, ele, time, ele_service)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    track_id, start_seq + i, p.lat, p.lon, p.ele, p.time,
                    p.ele_service,
                )
                for i, p in enumerate(points)
            ],
        )

    def get_points(self, track_id: int) -> list[Point]:
        rows = self.conn.execute(
            "SELECT lat, lon, ele, time, ele_service FROM points"
            " WHERE track_id = ? ORDER BY seq",
            (track_id,),
        ).fetchall()
        return [
            Point(r["lat"], r["lon"], r["ele"], r["time"], r["ele_service"])
            for r in rows
        ]

    def reverse_track(self, track_id: int) -> bool:
        """Inverse le sens de parcours d'une trace."""
        points = self.get_points(track_id)
        if len(points) < 2:
            return False
        self.replace_points(track_id, list(reversed(points)))
        return True

    def set_service_elevations(
        self, track_id: int, elevations: Sequence[float | None]
    ) -> int:
        """Enregistre les altitudes calculées par le service altimétrique.

        Retourne le nombre de points renseignés. Les points sans altitude
        (hors couverture du service) sont laissés vides.
        """
        # Les altitudes arrivent dans l'ordre des points, pas dans celui des
        # numéros de séquence : on relit ces derniers plutôt que de les supposer
        # consécutifs à partir de zéro.
        sequences = [
            row["seq"]
            for row in self.conn.execute(
                "SELECT seq FROM points WHERE track_id = ? ORDER BY seq",
                (track_id,),
            )
        ]
        with self.conn:
            renseignes = 0
            for seq, altitude in zip(sequences, elevations):
                if altitude is None:
                    continue
                self.conn.execute(
                    "UPDATE points SET ele_service = ? WHERE track_id = ? AND seq = ?",
                    (float(altitude), track_id, seq),
                )
                renseignes += 1
            self._touch(track_id)
        return renseignes

    def count_points(self, track_id: int) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM points WHERE track_id = ?", (track_id,)
        ).fetchone()
        return int(row["n"])

    def _next_seq(self, track_id: int) -> int:
        """Prochain numéro d'ordre libre pour cette trace."""
        row = self.conn.execute(
            "SELECT IFNULL(MAX(seq), -1) AS last FROM points WHERE track_id = ?",
            (track_id,),
        ).fetchone()
        return int(row["last"]) + 1

    def append_points(self, track_id: int, points: Sequence[Point]) -> None:
        """Ajoute des points à la fin de la trace (reprise de trace)."""
        if self.get_track(track_id) is None:
            raise NotFoundError(f"Trace {track_id} introuvable.")
        if not points:
            return
        with self.conn:
            self._insert_points(
                track_id, points, start_seq=self._next_seq(track_id)
            )
            self._touch(track_id)

    def replace_points(self, track_id: int, points: Sequence[Point]) -> None:
        """Remplace intégralement les points d'une trace (sauvegarde d'édition)."""
        if self.get_track(track_id) is None:
            raise NotFoundError(f"Trace {track_id} introuvable.")
        with self.conn:
            self.conn.execute("DELETE FROM points WHERE track_id = ?", (track_id,))
            self._insert_points(track_id, points, start_seq=0)
            self._touch(track_id)

    def close_track(self, track_id: int) -> bool:
        """Ferme la trace en boucle : ajoute le point de départ à la fin.

        Retourne True si un point a été ajouté, False si la boucle existait déjà
        ou si la trace compte moins de 3 points.
        """
        points = self.get_points(track_id)
        if len(points) < 3:
            return False
        already_closed = points[0].as_tuple() == points[-1].as_tuple()
        with self.conn:
            if not already_closed:
                # Le numéro d'ordre se lit en base plutôt que de se déduire du
                # nombre de points : une suite trouée écraserait un point.
                self._insert_points(
                    track_id, [points[0]], start_seq=self._next_seq(track_id)
                )
            self.conn.execute(
                "UPDATE tracks SET is_loop = 1, updated_at = datetime('now')"
                " WHERE id = ?",
                (track_id,),
            )
        return not already_closed

    def _touch(self, track_id: int) -> None:
        self.conn.execute(
            "UPDATE tracks SET updated_at = datetime('now') WHERE id = ?", (track_id,)
        )
