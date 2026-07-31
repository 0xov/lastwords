"""Durable SQLite snapshots for single-instance ephemeral hosts.

LAST WORDS keeps its hot database on the container's local filesystem so
SQLite retains real transactions and file locking. When
LASTWORDS_BACKUP_BUCKET is configured, every committed write is copied through
SQLite's online backup API and atomically replaced as one private Cloud Storage
object. A cold container restores that verified snapshot before app startup.

The deployment must still cap the service at one instance. Object generation
preconditions prevent an older revision from overwriting a newer snapshot.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import tempfile
import threading
from pathlib import Path
from typing import Any, Optional


log = logging.getLogger("lastwords.persistence")

_BACKUP_BUCKET = os.environ.get("LASTWORDS_BACKUP_BUCKET", "").strip()
_BACKUP_OBJECT = os.environ.get(
    "LASTWORDS_BACKUP_OBJECT",
    "lastwords.db",
).strip()
_ALLOW_EMPTY_BOOTSTRAP = os.environ.get(
    "LASTWORDS_ALLOW_EMPTY_BOOTSTRAP",
    "",
).strip().lower() in {"1", "true", "yes"}
_LOCK = threading.Lock()
_storage_client: Any = None
_generation: Optional[int] = None
_dirty = False


class PersistenceUnavailable(RuntimeError):
    """The local state is newer than its durable Cloud Storage snapshot."""


def configured() -> bool:
    return bool(_BACKUP_BUCKET)


def persistence_pending() -> bool:
    return configured() and _dirty


def _get_blob():
    global _storage_client

    from google.cloud import storage

    if _storage_client is None:
        _storage_client = storage.Client()
    return _storage_client.bucket(_BACKUP_BUCKET).blob(_BACKUP_OBJECT)


def _is_not_found(error: Exception) -> bool:
    code = getattr(error, "code", None)
    return (
        code == 404
        or error.__class__.__name__ == "NotFound"
        or "404" in str(error)
    )


def _verify_sqlite(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        result = conn.execute("PRAGMA integrity_check").fetchone()
    finally:
        conn.close()
    if result is None or result[0] != "ok":
        raise RuntimeError("Cloud database snapshot failed integrity_check")


def _temporary_snapshot_path(prefix: str) -> Path:
    descriptor, name = tempfile.mkstemp(prefix=prefix, suffix=".db")
    os.close(descriptor)
    return Path(name)


def restore_database(db_path: Path) -> bool:
    """Restore a private snapshot when the local database does not exist."""
    global _generation

    if not configured() or db_path.exists():
        return False

    with _LOCK:
        if db_path.exists():
            return False

        blob = _get_blob()
        try:
            blob.reload()
        except Exception as error:  # noqa: BLE001
            if _is_not_found(error):
                if not _ALLOW_EMPTY_BOOTSTRAP:
                    raise RuntimeError(
                        "Database snapshot is missing; refusing an implicit "
                        "WORLD 001 bootstrap"
                    ) from error
                _generation = 0
                log.info("No prior database snapshot; starting WORLD 001")
                return False
            raise

        observed_generation = int(blob.generation)
        temporary = _temporary_snapshot_path("lastwords-restore-")
        try:
            blob.download_to_filename(
                str(temporary),
                if_generation_match=observed_generation,
            )
            _verify_sqlite(temporary)
            db_path.parent.mkdir(parents=True, exist_ok=True)
            os.replace(temporary, db_path)
            _generation = observed_generation
            log.info("Restored database snapshot generation %s", _generation)
            return True
        finally:
            temporary.unlink(missing_ok=True)


def backup_database(source: sqlite3.Connection, db_path: Path) -> bool:
    """Upload one consistent SQLite snapshot after a committed mutation."""
    global _dirty, _generation

    if not configured():
        return False

    _dirty = True
    try:
        with _LOCK:
            blob = _get_blob()
            if _generation is None:
                try:
                    blob.reload()
                    _generation = int(blob.generation)
                except Exception as error:  # noqa: BLE001
                    if _is_not_found(error) and _ALLOW_EMPTY_BOOTSTRAP:
                        _generation = 0
                    else:
                        raise

            temporary = _temporary_snapshot_path("lastwords-backup-")
            destination = sqlite3.connect(temporary)
            try:
                source.backup(destination)
                destination.commit()
            finally:
                destination.close()

            try:
                _verify_sqlite(temporary)
                blob.upload_from_filename(
                    str(temporary),
                    content_type="application/vnd.sqlite3",
                    if_generation_match=_generation,
                    timeout=30,
                )
                if blob.generation is None:
                    blob.reload()
                _generation = int(blob.generation)
            finally:
                temporary.unlink(missing_ok=True)
    except Exception as error:  # noqa: BLE001
        log.exception("Durable database snapshot failed")
        raise PersistenceUnavailable(
            "The shared world cannot safely persist a new change"
        ) from error

    _dirty = False
    log.info(
        "Persisted database snapshot generation %s from %s",
        _generation,
        db_path.name,
    )
    return True
