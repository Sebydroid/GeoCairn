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

SCHEMA_VERSION = 2

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
    PRIMARY KEY (track_id, seq)
) WITHOUT ROWID;
"""


class DuplicateNameError(ValueError):
    """Un dossier du même nom existe déjà au même niveau."""


class NotFoundError(LookupError):
    """L'élément demandé n'existe pas."""


class CycleError(ValueError):
    """Le déplacement demandé rendrait un dossier descendant de lui-même."""


class Database:
    """Couche d'accès aux données.

    Utilisable comme gestionnaire de contexte :
        with Database() as db: ...
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else db_path()
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self._create_schema()

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

    def _migrate(self, version: int) -> None:
        """Met à niveau une base existante sans toucher aux données.

        `CREATE TABLE IF NOT EXISTS` n'ajoute pas les colonnes apparues après
        coup : il faut les poser explicitement.
        """
        if version >= SCHEMA_VERSION:
            return

        if version < 2:
            colonnes = {
                r["name"] for r in self.conn.execute("PRAGMA table_info(tracks)")
            }
            if "opacity" not in colonnes:
                self.conn.execute(
                    "ALTER TABLE tracks ADD COLUMN opacity REAL NOT NULL "
                    "DEFAULT 0.9"
                )

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

    def close(self) -> None:
        self.conn.close()

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
        with self.conn:
            self.conn.execute(
                "UPDATE tracks SET name = ?, updated_at = datetime('now')"
                " WHERE id = ?",
                (name, track_id),
            )

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
        with self.conn:
            self.conn.execute(
                "UPDATE tracks SET folder_id = ?, updated_at = datetime('now')"
                " WHERE id = ?",
                (folder_id, track_id),
            )

    def delete_track(self, track_id: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM tracks WHERE id = ?", (track_id,))

    # ------------------------------------------------- duplication, découpage

    def duplicate_track(self, track_id: int, name: str | None = None) -> int:
        """Copie une trace avec ses points, dans le même dossier."""
        track = self.get_track(track_id, with_points=True)
        if track is None:
            raise NotFoundError(f"Trace {track_id} introuvable.")
        return self.create_track(
            name if name is not None else f"{track.name} (copie)",
            folder_id=track.folder_id,
            points=track.points,
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
            "INSERT INTO points(track_id, seq, lat, lon, ele, time)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            [
                (track_id, start_seq + i, p.lat, p.lon, p.ele, p.time)
                for i, p in enumerate(points)
            ],
        )

    def get_points(self, track_id: int) -> list[Point]:
        rows = self.conn.execute(
            "SELECT lat, lon, ele, time FROM points WHERE track_id = ? ORDER BY seq",
            (track_id,),
        ).fetchall()
        return [Point(r["lat"], r["lon"], r["ele"], r["time"]) for r in rows]

    def count_points(self, track_id: int) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM points WHERE track_id = ?", (track_id,)
        ).fetchone()
        return int(row["n"])

    def append_points(self, track_id: int, points: Sequence[Point]) -> None:
        """Ajoute des points à la fin de la trace (reprise de trace)."""
        if self.get_track(track_id) is None:
            raise NotFoundError(f"Trace {track_id} introuvable.")
        if not points:
            return
        row = self.conn.execute(
            "SELECT IFNULL(MAX(seq), -1) AS last FROM points WHERE track_id = ?",
            (track_id,),
        ).fetchone()
        with self.conn:
            self._insert_points(track_id, points, start_seq=int(row["last"]) + 1)
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
                self._insert_points(track_id, [points[0]], start_seq=len(points))
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
