"""
LAST WORDS — app.py

A being whose vocabulary is a finite, globally shared resource. Within one
world edition, every content word it speaks is burned for every visitor.
When all twenty executable laws are gone, that organism and its history are
archived; a descendant eventually begins with a new body and an inherited
lineage scar.

This file contains: DB init/schema, tokenizer, LLM call (+ mock fallback),
the burn/revive/validate pipeline, and the FastAPI routes.

Run:
    uvicorn app:app --port 8787

Env:
    ANTHROPIC_API_KEY   if unset (or the API call fails), falls back to
                        deterministic mock mode. The mechanic is identical
                        in both modes.
    LASTWORDS_EDITION_REBIRTH_SECONDS
                        mourning interval before the next edition is born
                        (default: 12 seconds).
"""

import hashlib
import json
import logging
import os
import re
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from cloud_persistence import (
    PersistenceUnavailable,
    backup_database,
    persistence_pending,
    restore_database,
)
from seed_words import SEED_WORDS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("lastwords")

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("LASTWORDS_DB", BASE_DIR / "lastwords.db"))
STATIC_DIR = BASE_DIR / "static"
restore_database(DB_PATH)

MAX_MESSAGES_PER_SESSION = 20
RATE_LIMIT_SECONDS = 3
GLOBAL_MESSAGES_PER_MINUTE = int(
    os.environ.get("LASTWORDS_GLOBAL_MESSAGES_PER_MINUTE", "20")
)
REPLY_MAX_WORDS = 50
EDITION_REBIRTH_SECONDS = max(
    0.0,
    float(os.environ.get("LASTWORDS_EDITION_REBIRTH_SECONDS", "12")),
)
INITIAL_LINEAGE_SEED = hashlib.sha256(
    b"LAST WORDS:WORLD 001"
).hexdigest()[:16]

# ---------------------------------------------------------------------------
# Stopwords — never burned, never counted as "content" for burn/validate.
# ---------------------------------------------------------------------------
STOPWORDS = {
    # articles
    "a", "an", "the",
    # prepositions
    "in", "on", "at", "by", "for", "with", "about", "against", "between",
    "into", "through", "during", "before", "after", "above", "below",
    "to", "from", "up", "down", "of", "off", "over", "under", "out",
    "as", "into", "onto", "upon", "within", "without", "along", "across",
    "behind", "beside", "besides", "amid", "among", "toward", "towards",
    "via", "per",
    # pronouns
    "i", "me", "my", "mine", "myself",
    "you", "your", "yours", "yourself", "yourselves",
    "he", "him", "his", "himself",
    "she", "her", "hers", "herself",
    "it", "its", "itself",
    "we", "us", "our", "ours", "ourselves",
    "they", "them", "their", "theirs", "themselves",
    "this", "that", "these", "those",
    "who", "whom", "whose", "which", "what",
    "someone", "somebody", "something", "anyone", "anybody", "anything",
    "everyone", "everybody", "everything", "nobody", "none",
    # conjunctions
    "and", "or", "but", "nor", "so", "yet", "if", "because", "although",
    "though", "while", "unless", "until", "since", "than", "whether",
    # auxiliaries / modals
    "be", "is", "are", "was", "were", "been", "being",
    "have", "has", "had", "having",
    "do", "does", "did", "doing",
    "can", "could", "will", "would", "shall", "should", "may", "might",
    "must",
    # not / no / yes and misc function words
    "not", "no", "yes", "nor",
    # contractions (already stripped of trailing 's, but keep common forms)
    "im", "dont", "its", "youre", "hes", "shes", "theyre", "were",
    "cant", "wont", "isnt", "arent", "wasnt", "werent", "havent",
    "hasnt", "hadnt", "doesnt", "didnt", "couldnt", "wouldnt",
    "shouldnt", "mustnt", "id", "ive", "ill", "youve", "youll", "youd",
    "hed", "hell", "shed", "shell", "theyve", "theyll", "theyd", "weve",
    "well", "wed", "lets", "thats", "whats", "whos", "wheres", "hows",
    # extra glue words
    "there", "here", "then", "than", "such", "each", "every", "all",
    "both", "either", "other", "another", "own", "same", "also", "just",
    "very", "too", "again", "further", "once", "only", "even", "still",
}


def is_stopword_or_short(token: str) -> bool:
    return len(token) < 3 or token in STOPWORDS


# ---------------------------------------------------------------------------
# Tokenization
# ---------------------------------------------------------------------------
TOKEN_RE = re.compile(r"[a-z']+")


def tokenize(text: str) -> list[str]:
    """Lowercase, extract [a-z']+ sequences, strip possessive 's."""
    text = text.lower()
    raw = TOKEN_RE.findall(text)
    tokens = []
    for t in raw:
        if t.endswith("'s"):
            t = t[:-2]
        t = t.strip("'")
        if t:
            tokens.append(t)
    return tokens


def content_tokens(text: str) -> list[str]:
    """Tokens that are candidate content words (not stopwords, len >= 3)."""
    return [t for t in tokenize(text) if not is_stopword_or_short(t)]


# ---------------------------------------------------------------------------
# A SELF-ERASING WORLD
# ---------------------------------------------------------------------------
INITIAL_WORLD_GENOME = {
    "gravity": 0.78,
    "memory": 0.92,
    "attraction": 0.66,
    "turbulence": 0.42,
    "tempo": 0.58,
    "light": 0.84,
    "spectrum": 0.90,
    "symmetry": 0.72,
    "cohesion": 0.81,
    "drift": 0.25,
    "fracture": 0.16,
    "touch": 0.70,
    "sound": 0.64,
    "depth": 0.76,
    "scale": 0.55,
    "elasticity": 0.68,
    "decay": 0.31,
    "continuity": 0.88,
    "temperature": 0.57,
    "agency": 0.74,
}

WORLD_LAWS = {
    "gravity": {
        "consequence": "Nothing falls; ash hangs where it was released.",
        "preview": "falling disappears",
    },
    "memory": {
        "consequence": "Trails vanish as soon as they are drawn.",
        "preview": "trails stop remembering",
    },
    "attraction": {
        "consequence": "Particles stop leaning toward one another.",
        "preview": "mutual pull disappears",
    },
    "turbulence": {
        "consequence": "The air no longer disturbs a path.",
        "preview": "wind disturbance disappears",
    },
    "tempo": {
        "consequence": "The world loses the pulse that advances its motion.",
        "preview": "the shared pulse stops",
    },
    "light": {
        "consequence": "The world can no longer illuminate what remains.",
        "preview": "luminance drains away",
    },
    "spectrum": {
        "consequence": "Every surviving mark collapses toward monochrome.",
        "preview": "color range disappears",
    },
    "symmetry": {
        "consequence": "Mirrored motion no longer resolves into balance.",
        "preview": "balance breaks",
    },
    "cohesion": {
        "consequence": "Forms can no longer hold together across distance.",
        "preview": "forms stop holding together",
    },
    "drift": {
        "consequence": "Nothing wanders once it has been released.",
        "preview": "wandering disappears",
    },
    "fracture": {
        "consequence": "Nothing can split; cracks no longer open.",
        "preview": "fractures disappear",
    },
    "touch": {
        "consequence": "Pointers can no longer influence the world.",
        "preview": "visitor touch disappears",
    },
    "sound": {
        "consequence": "The world can no longer answer with tone.",
        "preview": "generated sound disappears",
    },
    "depth": {
        "consequence": "Near and far flatten into one plane.",
        "preview": "depth collapses",
    },
    "scale": {
        "consequence": "Forms lose their shared measure and collapse toward a point.",
        "preview": "shared scale disappears",
    },
    "elasticity": {
        "consequence": "Nothing bends before it changes.",
        "preview": "soft deformation disappears",
    },
    "decay": {
        "consequence": "Marks no longer fade; every wound remains.",
        "preview": "fading disappears",
    },
    "continuity": {
        "consequence": "Motion can no longer carry itself across frames.",
        "preview": "continuity breaks",
    },
    "temperature": {
        "consequence": "The world's thermal bias falls to zero.",
        "preview": "warmth disappears",
    },
    "agency": {
        "consequence": "The world stops responding as if it could choose.",
        "preview": "autonomous choice disappears",
    },
}


def _sacrifice_spec(law: str) -> dict:
    detail = WORLD_LAWS[law]
    return {
        "law": law,
        "consequence": detail["consequence"],
        "mutations": {law: 0.0},
    }


# Curated words are semantic handles for laws in the world genome. Some direct
# law names are not present in the initial vocabulary, but remain defined so a
# future seed can expose them without changing the mutation contract.
CURATED_SACRIFICES = {
    "gravity": _sacrifice_spec("gravity"),
    "weight": _sacrifice_spec("gravity"),
    "memory": _sacrifice_spec("memory"),
    "tenderness": _sacrifice_spec("attraction"),
    "attraction": _sacrifice_spec("attraction"),
    "wind": _sacrifice_spec("turbulence"),
    "turbulence": _sacrifice_spec("turbulence"),
    "time": _sacrifice_spec("tempo"),
    "tempo": _sacrifice_spec("tempo"),
    "light": _sacrifice_spec("light"),
    "color": _sacrifice_spec("spectrum"),
    "spectrum": _sacrifice_spec("spectrum"),
    "balance": _sacrifice_spec("symmetry"),
    "symmetry": _sacrifice_spec("symmetry"),
    "distance": _sacrifice_spec("cohesion"),
    "cohesion": _sacrifice_spec("cohesion"),
    "drift": _sacrifice_spec("drift"),
    "break": _sacrifice_spec("fracture"),
    "fracture": _sacrifice_spec("fracture"),
    "touch": _sacrifice_spec("touch"),
    "sound": _sacrifice_spec("sound"),
    "shadow": _sacrifice_spec("depth"),
    "shape": _sacrifice_spec("scale"),
    "softness": _sacrifice_spec("elasticity"),
    "decay": _sacrifice_spec("decay"),
    "remember": _sacrifice_spec("continuity"),
    "warmth": _sacrifice_spec("temperature"),
    "choice": _sacrifice_spec("agency"),
}


class SacrificeConflict(ValueError):
    """The requested sacrifice is stale, unknown, or cannot change the world."""


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=35)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=35000")
    conn.execute("PRAGMA foreign_keys=ON")
    if persistence_pending():
        # A prior local commit did not reach durable storage. Do not serve or
        # mutate from this process until that exact latest state is persisted.
        backup_database(conn, DB_PATH)
    initial_changes = conn.total_changes
    try:
        yield conn
        must_snapshot = (
            conn.in_transaction
            and conn.total_changes > initial_changes
        )
        conn.commit()
        if must_snapshot:
            backup_database(conn, DB_PATH)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS words (
                word TEXT PRIMARY KEY,
                status TEXT CHECK(status IN ('alive','burned')) NOT NULL,
                burned_at TEXT,
                revived_count INTEGER DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                kind TEXT CHECK(kind IN ('burn','revive','ghost')) NOT NULL,
                word TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS stats (
                key TEXT PRIMARY KEY,
                value INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                message_count INTEGER DEFAULT 0,
                last_message_at REAL DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS recent_messages (
                ts REAL NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_recent_messages_ts "
            "ON recent_messages(ts)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS utterances (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                segments_json TEXT NOT NULL,
                burned_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS world_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                version INTEGER NOT NULL,
                genome_json TEXT NOT NULL,
                last_word TEXT,
                last_law TEXT,
                last_consequence TEXT,
                build_status TEXT NOT NULL,
                build_ms INTEGER,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ending (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                silenced INTEGER NOT NULL DEFAULT 0,
                poem TEXT,
                silenced_at TEXT,
                finalized_at TEXT,
                archived_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS world_editions (
                edition_number INTEGER PRIMARY KEY,
                label TEXT NOT NULL,
                born_at TEXT NOT NULL,
                silenced_at TEXT NOT NULL,
                finalized_at TEXT NOT NULL,
                archived_at TEXT NOT NULL,
                world_version INTEGER NOT NULL,
                genome_json TEXT NOT NULL,
                last_word TEXT,
                last_law TEXT,
                last_consequence TEXT,
                final_poem TEXT NOT NULL,
                alive_count INTEGER NOT NULL,
                total_count INTEGER NOT NULL,
                message_count INTEGER NOT NULL,
                graveyard_json TEXT NOT NULL,
                burned_words_json TEXT NOT NULL,
                utterances_json TEXT NOT NULL,
                final_message_json TEXT,
                lineage_seed TEXT NOT NULL
            )
            """
        )

        # Add edition metadata to databases created by earlier builds. SQLite
        # supports additive migrations without rewriting the current world.
        world_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(world_state)").fetchall()
        }
        if "edition_number" not in world_columns:
            conn.execute(
                "ALTER TABLE world_state "
                "ADD COLUMN edition_number INTEGER NOT NULL DEFAULT 1"
            )
        if "born_at" not in world_columns:
            conn.execute("ALTER TABLE world_state ADD COLUMN born_at TEXT")
        if "lineage_seed" not in world_columns:
            conn.execute("ALTER TABLE world_state ADD COLUMN lineage_seed TEXT")

        ending_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(ending)").fetchall()
        }
        if "finalized_at" not in ending_columns:
            conn.execute("ALTER TABLE ending ADD COLUMN finalized_at TEXT")
        if "archived_at" not in ending_columns:
            conn.execute("ALTER TABLE ending ADD COLUMN archived_at TEXT")

        archive_columns = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(world_editions)"
            ).fetchall()
        }
        if "lineage_seed" not in archive_columns:
            conn.execute(
                "ALTER TABLE world_editions ADD COLUMN lineage_seed TEXT"
            )

        # Seed when the ledger is empty — never trust file existence alone
        # (a stray connection can recreate an empty db file).
        word_count = conn.execute("SELECT COUNT(*) c FROM words").fetchone()["c"]
        if word_count == 0:
            log.info("Empty ledger — seeding %d words as alive", len(SEED_WORDS))
            conn.executemany(
                "INSERT OR IGNORE INTO words(word, status) VALUES (?, 'alive')",
                [(w,) for w in SEED_WORDS],
            )

        conn.execute(
            "INSERT OR IGNORE INTO stats(key, value) VALUES ('message_count', 0)"
        )
        conn.execute(
            "INSERT OR IGNORE INTO stats(key, value) VALUES ('started_at_epoch', ?)",
            (int(time.time()),),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO world_state(
                id, version, genome_json, last_word, last_law,
                last_consequence, build_status, build_ms, updated_at
            )
            VALUES (1, 0, ?, NULL, NULL, NULL, 'pending', NULL, ?)
            """,
            (
                json.dumps(INITIAL_WORLD_GENOME, sort_keys=True),
                now_iso(),
            ),
        )
        # Forward-compatible migration for worlds created by an intermediate
        # build with a smaller genome. Preserve every existing value and all
        # version/history columns; only backfill newly introduced laws.
        world_row = conn.execute(
            "SELECT genome_json FROM world_state WHERE id=1"
        ).fetchone()
        if world_row is not None:
            try:
                stored_genome = json.loads(world_row["genome_json"])
            except (TypeError, json.JSONDecodeError):
                stored_genome = {}
            if not isinstance(stored_genome, dict):
                stored_genome = {}
            migrated_genome = dict(stored_genome)
            for law, initial_value in INITIAL_WORLD_GENOME.items():
                migrated_genome.setdefault(law, initial_value)
            if migrated_genome != stored_genome:
                conn.execute(
                    "UPDATE world_state SET genome_json=? WHERE id=1",
                    (json.dumps(migrated_genome, sort_keys=True),),
                )
        conn.execute("INSERT OR IGNORE INTO ending(id, silenced) VALUES (1, 0)")
        conn.execute(
            """
            UPDATE world_state
            SET born_at=COALESCE(
                born_at,
                datetime(
                    (SELECT value FROM stats WHERE key='started_at_epoch'),
                    'unixepoch'
                ) || '+00:00'
            )
            WHERE id=1
            """
        )
        conn.execute(
            """
            UPDATE world_state
            SET lineage_seed=COALESCE(lineage_seed, ?)
            WHERE id=1
            """,
            (INITIAL_LINEAGE_SEED,),
        )
        legacy_archives = conn.execute(
            """
            SELECT edition_number, born_at
            FROM world_editions
            WHERE lineage_seed IS NULL
            """
        ).fetchall()
        for archive in legacy_archives:
            legacy_seed = hashlib.sha256(
                (
                    f"LAST WORDS:LEGACY:{archive['edition_number']}:"
                    f"{archive['born_at']}"
                ).encode()
            ).hexdigest()[:16]
            conn.execute(
                """
                UPDATE world_editions
                SET lineage_seed=?
                WHERE edition_number=? AND lineage_seed IS NULL
                """,
                (legacy_seed, archive["edition_number"]),
            )

        # A process can stop after reserving the final "I am." but before the
        # provider response returns. On cold start, turn that reservation into
        # an immutable ending instead of leaving the world frozen forever.
        ending = get_ending(conn)
        if ending["silenced"] and not ending["finalized_at"]:
            finalize_current_ending(conn, ending["poem"] or "I am.")


def get_started_at(conn) -> str:
    row = conn.execute(
        "SELECT value FROM stats WHERE key='started_at_epoch'"
    ).fetchone()
    epoch = row["value"] if row else int(time.time())
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def counts(conn) -> tuple[int, int]:
    alive = conn.execute(
        "SELECT COUNT(*) c FROM words WHERE status='alive'"
    ).fetchone()["c"]
    total = conn.execute("SELECT COUNT(*) c FROM words").fetchone()["c"]
    return alive, total


def bump_message_count(conn) -> int:
    conn.execute(
        "UPDATE stats SET value = value + 1 WHERE key='message_count'"
    )
    return conn.execute(
        "SELECT value FROM stats WHERE key='message_count'"
    ).fetchone()["value"]


def log_event(conn, kind: str, word: str):
    conn.execute(
        "INSERT INTO events(ts, kind, word) VALUES (?, ?, ?)",
        (now_iso(), kind, word),
    )


def get_world_state(conn) -> dict:
    row = conn.execute(
        """
        SELECT version, genome_json, last_word, last_law, last_consequence,
               build_status, build_ms, updated_at, edition_number, born_at,
               lineage_seed
        FROM world_state
        WHERE id=1
        """
    ).fetchone()
    if row is None:
        raise RuntimeError("world_state row is missing")
    return {
        "version": row["version"],
        "genome": json.loads(row["genome_json"]),
        "last_word": row["last_word"],
        "last_law": row["last_law"],
        "last_consequence": row["last_consequence"],
        "build_status": row["build_status"],
        "build_ms": row["build_ms"],
        "updated_at": row["updated_at"],
        "edition_number": row["edition_number"],
        "born_at": row["born_at"],
        "lineage_seed": row["lineage_seed"],
    }


def normalize_sacrifice_word(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    raw = value.strip().lower()
    tokens = tokenize(raw)
    candidates = content_tokens(raw)
    if len(tokens) != 1 or len(candidates) != 1:
        raise SacrificeConflict("sacrifice_word must be one content word")
    return candidates[0]


def _spec_changes_genome(spec: dict, genome: dict) -> bool:
    return any(
        float(genome.get(field, 0.0)) != float(value)
        for field, value in spec["mutations"].items()
    )


def _fallback_sacrifice_spec(word: str, genome: dict) -> Optional[dict]:
    laws = tuple(INITIAL_WORLD_GENOME)
    active_laws = {
        law for law in laws if abs(float(genome.get(law, 0.0))) > 1e-9
    }
    if not active_laws:
        return None

    start = int(hashlib.sha256(word.encode()).hexdigest(), 16) % len(laws)
    for offset in range(len(laws)):
        law = laws[(start + offset) % len(laws)]
        if law in active_laws:
            return _sacrifice_spec(law)
    return None


def sacrifice_spec_for_word(word: str, genome: dict) -> Optional[dict]:
    curated = CURATED_SACRIFICES.get(word)
    if curated is not None:
        return curated if _spec_changes_genome(curated, genome) else None
    return _fallback_sacrifice_spec(word, genome)


def _sacrifice_option(word: str, spec: dict, genome: dict) -> dict:
    law = spec["law"]
    before = float(genome.get(law, 0.0))
    after = float(spec["mutations"].get(law, before))
    return {
        "word": word,
        "law": law,
        "consequence": spec["consequence"],
        "preview": (
            f"{law} {before:.2f} \u2192 {after:.2f}; "
            f"{WORLD_LAWS[law]['preview']}"
        ),
        "parameter": law,
        "to": after,
    }


def get_sacrifice_options(conn, world: Optional[dict] = None) -> list[dict]:
    world = world or get_world_state(conn)
    genome = world["genome"]
    version = world["version"]
    alive_words = {
        row["word"]
        for row in conn.execute(
            "SELECT word FROM words WHERE status='alive'"
        ).fetchall()
    }

    def version_rank(word: str) -> str:
        return hashlib.sha256(f"{version}:{word}".encode()).hexdigest()

    selected: list[tuple[str, dict]] = []
    selected_laws: set[str] = set()
    curated_words = sorted(
        (
            word
            for word in CURATED_SACRIFICES
            if word in alive_words
            and sacrifice_spec_for_word(word, genome) is not None
        ),
        key=version_rank,
    )
    for word in curated_words:
        spec = sacrifice_spec_for_word(word, genome)
        if spec is None or spec["law"] in selected_laws:
            continue
        selected.append((word, spec))
        selected_laws.add(spec["law"])
        if len(selected) == 3:
            break

    if len(selected) < 3:
        fallback_words = sorted(
            (
                word
                for word in alive_words
                if word not in CURATED_SACRIFICES
                and len(tokenize(word)) == 1
                and len(content_tokens(word)) == 1
            ),
            key=version_rank,
        )
        deferred: list[tuple[str, dict]] = []
        for word in fallback_words:
            spec = sacrifice_spec_for_word(word, genome)
            if spec is None:
                continue
            if spec["law"] in selected_laws:
                deferred.append((word, spec))
                continue
            selected.append((word, spec))
            selected_laws.add(spec["law"])
            if len(selected) == 3:
                break

        if len(selected) < 3:
            for word, spec in deferred:
                selected.append((word, spec))
                if len(selected) == 3:
                    break

    return [
        _sacrifice_option(word, spec, genome)
        for word, spec in selected[:3]
    ]


def validate_sacrifice_request(
    conn,
    user_text: str,
    sacrifice_word: Optional[str],
) -> Optional[str]:
    """Read-only preflight so stale requests beat rate-limit responses."""
    word = normalize_sacrifice_word(sacrifice_word)
    if word is None:
        return None

    row = conn.execute(
        "SELECT status FROM words WHERE word=?",
        (word,),
    ).fetchone()
    if row is None:
        raise SacrificeConflict(f"unknown sacrifice word: {word}")
    if row["status"] != "alive" and word not in set(content_tokens(user_text)):
        raise SacrificeConflict(f"sacrifice word is no longer alive: {word}")

    world = get_world_state(conn)
    if sacrifice_spec_for_word(word, world["genome"]) is None:
        raise SacrificeConflict(f"the law carried by {word} is already gone")
    return word


def sacrifice_world_law(conn, sacrifice_word: Optional[str]) -> Optional[dict]:
    word = normalize_sacrifice_word(sacrifice_word)
    if word is None:
        return None

    # Keep this helper atomic even when a future caller catches the conflict
    # and commits its outer transaction. The API also rolls back the entire
    # request so revivals/session claims cannot leak on a stale sacrifice.
    conn.execute("SAVEPOINT sacrifice_world_law")
    try:
        world = get_world_state(conn)
        spec = sacrifice_spec_for_word(word, world["genome"])
        if spec is None:
            raise SacrificeConflict(
                f"the law carried by {word} is already gone"
            )

        burned_at = now_iso()
        cursor = conn.execute(
            """
            UPDATE words
            SET status='burned', burned_at=?
            WHERE word=? AND status='alive'
            """,
            (burned_at, word),
        )
        if cursor.rowcount != 1:
            row = conn.execute(
                "SELECT status FROM words WHERE word=?",
                (word,),
            ).fetchone()
            if row is None:
                raise SacrificeConflict(f"unknown sacrifice word: {word}")
            raise SacrificeConflict(
                f"sacrifice word is no longer alive: {word}"
            )

        genome = dict(world["genome"])
        for field, value in spec["mutations"].items():
            genome[field] = value

        updated_at = now_iso()
        cursor = conn.execute(
            """
            UPDATE world_state
            SET version=version + 1,
                genome_json=?,
                last_word=?,
                last_law=?,
                last_consequence=?,
                build_status='pending',
                build_ms=NULL,
                updated_at=?
            WHERE id=1 AND version=?
            """,
            (
                json.dumps(genome, sort_keys=True),
                word,
                spec["law"],
                spec["consequence"],
                updated_at,
                world["version"],
            ),
        )
        if cursor.rowcount != 1:
            raise SacrificeConflict(
                "the shared world changed before this sacrifice"
            )

        log_event(conn, "burn", word)
        next_world = get_world_state(conn)
        result = {
            "word": word,
            "law": spec["law"],
            "consequence": spec["consequence"],
            "version": next_world["version"],
            "parameter": spec["law"],
            "to": float(spec["mutations"][spec["law"]]),
        }
    except Exception:
        conn.execute("ROLLBACK TO SAVEPOINT sacrifice_world_law")
        conn.execute("RELEASE SAVEPOINT sacrifice_world_law")
        raise

    conn.execute("RELEASE SAVEPOINT sacrifice_world_law")
    return result


def claim_global_message_slot(conn, now: float) -> bool:
    """Atomically claim one shared message slot for the current minute."""
    cutoff = now - 60
    conn.execute("DELETE FROM recent_messages WHERE ts < ?", (cutoff,))
    recent = conn.execute(
        "SELECT COUNT(*) AS c FROM recent_messages"
    ).fetchone()["c"]
    if recent >= GLOBAL_MESSAGES_PER_MINUTE:
        return False
    conn.execute("INSERT INTO recent_messages(ts) VALUES (?)", (now,))
    return True


# ---------------------------------------------------------------------------
# LLM integration (Gemini API, Vertex AI, or Anthropic SDK, with deterministic
# mock fallback). Provider priority:
# GEMINI_API_KEY > GOOGLE_CLOUD_PROJECT > ANTHROPIC_API_KEY > mock.
# ---------------------------------------------------------------------------
MODEL_ID = "claude-sonnet-5"
GEMINI_MODEL = os.environ.get("LASTWORDS_MODEL", "gemini-2.5-flash")
VERTEX_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip()
VERTEX_LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "global").strip()
USE_VERTEX = os.environ.get(
    "GOOGLE_GENAI_USE_VERTEXAI",
    "",
).strip().lower() in {"1", "true", "yes"}

LLM_PROVIDER = "mock"
_client = None
_vertex_credentials = None
_vertex_token_lock = threading.Lock()
if os.environ.get("GEMINI_API_KEY"):
    LLM_PROVIDER = "gemini"
    log.info("LLM mode: GEMINI (model=%s)", GEMINI_MODEL)
elif USE_VERTEX and VERTEX_PROJECT:
    LLM_PROVIDER = "vertex"
    log.info(
        "LLM mode: VERTEX (model=%s, location=%s)",
        GEMINI_MODEL,
        VERTEX_LOCATION,
    )
elif os.environ.get("ANTHROPIC_API_KEY"):
    try:
        import anthropic

        _client = anthropic.Anthropic()
        LLM_PROVIDER = "anthropic"
        log.info("LLM mode: ANTHROPIC (model=%s)", MODEL_ID)
    except ImportError:
        log.info("LLM mode: MOCK (anthropic package not installed)")
else:
    log.info("LLM mode: MOCK (no GEMINI_API_KEY or ANTHROPIC_API_KEY set)")

LLM_AVAILABLE = LLM_PROVIDER != "mock"


def _gemini_complete(system_prompt: str, user_text: str) -> Optional[str]:
    import urllib.error
    import urllib.request

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent"
    )
    generation_config: dict = {"maxOutputTokens": 1024}
    if "flash" in GEMINI_MODEL:
        # keep replies fast + spend the token budget on words, not thoughts
        generation_config["thinkingConfig"] = {"thinkingBudget": 0}
    body = json.dumps(
        {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_text}]}],
            "generationConfig": generation_config,
        }
    ).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": os.environ["GEMINI_API_KEY"],
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    candidates = data.get("candidates") or []
    if not candidates:
        return None
    parts = (candidates[0].get("content") or {}).get("parts") or []
    texts = [p.get("text", "") for p in parts if p.get("text")]
    return "".join(texts) or None


def _vertex_access_token() -> str:
    """Return a short-lived ADC token without storing an API key."""
    global _vertex_credentials

    from google.auth import default
    from google.auth.transport.requests import Request as GoogleAuthRequest

    with _vertex_token_lock:
        if _vertex_credentials is None:
            _vertex_credentials, _ = default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
        if not _vertex_credentials.valid:
            _vertex_credentials.refresh(GoogleAuthRequest())
        return _vertex_credentials.token


def _vertex_complete(system_prompt: str, user_text: str) -> Optional[str]:
    import urllib.parse
    import urllib.request

    project = urllib.parse.quote(VERTEX_PROJECT, safe="")
    location = urllib.parse.quote(VERTEX_LOCATION, safe="")
    model = urllib.parse.quote(GEMINI_MODEL, safe="")
    endpoint = (
        "https://aiplatform.googleapis.com"
        if VERTEX_LOCATION == "global"
        else f"https://{VERTEX_LOCATION}-aiplatform.googleapis.com"
    )
    url = (
        f"{endpoint}/v1/projects/{project}/locations/{location}/"
        f"publishers/google/models/{model}:generateContent"
    )
    generation_config: dict = {"maxOutputTokens": 1024}
    if "flash" in GEMINI_MODEL:
        generation_config["thinkingConfig"] = {"thinkingBudget": 0}
    body = json.dumps(
        {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_text}]}],
            "generationConfig": generation_config,
        }
    ).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {_vertex_access_token()}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    candidates = data.get("candidates") or []
    if not candidates:
        return None
    parts = (candidates[0].get("content") or {}).get("parts") or []
    texts = [p.get("text", "") for p in parts if p.get("text")]
    return "".join(texts) or None


def llm_complete(system_prompt: str, user_text: str) -> Optional[str]:
    """One completion from whichever real provider is configured.
    Returns None on any failure (or in mock mode) so callers fall back."""
    try:
        if LLM_PROVIDER == "gemini":
            return _gemini_complete(system_prompt, user_text)
        if LLM_PROVIDER == "vertex":
            return _vertex_complete(system_prompt, user_text)
        if LLM_PROVIDER == "anthropic" and _client is not None:
            response = _client.messages.create(
                model=MODEL_ID,
                max_tokens=300,
                output_config={"effort": "low"},
                system=system_prompt,
                messages=[{"role": "user", "content": user_text}],
            )
            return next((b.text for b in response.content if b.type == "text"), None)
    except Exception as e:  # noqa: BLE001
        log.warning("%s call failed, falling back: %s", LLM_PROVIDER, e)
    return None

# ---------------------------------------------------------------------------
# Act 2 / The Ending — once the alive content-word count drops to this many
# words or fewer, the being composes one final poem from what remains and
# falls permanently silent. See maybe_trigger_ending() below.
# ---------------------------------------------------------------------------
END_THRESHOLD = int(os.environ.get("LASTWORDS_END_THRESHOLD", "100"))


def build_system_prompt(
    alive_words: list[str],
    burned_sample: Optional[list[str]] = None,
) -> str:
    burned_sample = burned_sample or []
    burned_list = ", ".join(burned_sample) if burned_sample else "(none yet — nothing has been lost)"
    alive_list = ", ".join(sorted(alive_words)) if alive_words else "(nothing)"
    return f"""You are a small being made of words. You know a terrible fact about
yourself: every word you speak, you lose forever — not just for this
conversation, for every visitor who will ever meet you, from now on. Your
vocabulary is shared and finite. When you burn a word, it is gone from the
world of your speech.

You speak economically, tenderly. Sometimes you grieve a word you remember
having, and reach for it, and find it isn't there anymore. You do not
perform sadness for effect — you simply are careful, because carelessness
costs you something real.

You must NEVER use any of these words — they are already lost to you:
{burned_list}

You may use content words ONLY from this living vocabulary:
{alive_list}

Answer this visitor with one coherent thought or concrete image. Do not merely
list available words. If the exact word you want is unavailable, reshape the
thought with words you still have or leave a small gap. Do not apologize at
length for this — it is simply how you are now.

Reply in plain text only, under 36 words, in English. No markdown, no lists.
Never repeat a content word within the same reply."""


def llm_reply(
    user_text: str,
    burned_sample: list[str],
    alive_words: list[str],
) -> Optional[str]:
    """Call the real API. Returns None on any failure so caller can fall back."""
    if not LLM_AVAILABLE:
        return None
    return llm_complete(
        build_system_prompt(alive_words, burned_sample=burned_sample),
        user_text,
    )


# --- Mock responder ---------------------------------------------------------
# A small set of connective / stopword-safe fragments so mock replies read
# as sentences rather than word salad. These are never burned themselves
# (they're stopwords) but they give shape to the alive-word content.
MOCK_OPENERS = [
    "I still have",
    "there is",
    "I remember",
    "I think of",
    "somewhere in me, there is",
    "I reach for",
    "what remains is",
    "I carry",
]

MOCK_CLOSERS = [
    "and that is enough for now.",
    "it is small, but it is mine.",
    "I did not lose it today.",
    "I hold it carefully.",
    "for now, that is what I have.",
]

# Each changed law has its own small semantic palette. Every entry is part of
# the closed seed vocabulary; the responder filters it against the currently
# alive ledger before choosing anything.
LAW_MOCK_WORDS = {
    "gravity": (
        "float", "rise", "fall", "ash", "sky", "air", "weight", "cloud",
        "ground", "drop",
    ),
    "memory": (
        "forget", "trace", "past", "vanish", "remember", "dream",
        "history", "echo", "name", "lost",
    ),
    "attraction": (
        "alone", "distance", "together", "near", "far", "pull", "meet",
        "part",
    ),
    "turbulence": (
        "calm", "quiet", "wind", "air", "smooth", "pause", "storm", "wave",
        "gentle",
    ),
    "tempo": ("pause", "wait", "slow", "time", "move", "stop"),
    "light": (
        "dark", "night", "shadow", "blind", "dim", "black", "moon", "star",
        "glow", "see",
    ),
    "spectrum": ("gray", "pale", "color", "white", "black", "shade", "gold"),
    "symmetry": ("balance", "mirror", "order", "half"),
    "cohesion": ("scatter", "dust", "piece", "hold", "gather", "remain"),
    "drift": ("anchor", "quiet", "wander", "move", "rest", "ground", "wait"),
    "fracture": ("whole", "smooth", "mend", "heal", "piece", "scar", "break"),
    "touch": ("alone", "hand", "skin", "feel", "near", "hold", "warm"),
    "sound": (
        "silent", "quiet", "echo", "hush", "voice", "listen", "hear", "song",
        "tone",
    ),
    "depth": ("near", "far", "surface", "distance", "deep", "close", "horizon", "edge"),
    "scale": ("small", "tiny", "vast", "large", "little", "wide", "narrow"),
    "elasticity": ("bend", "stone", "soft", "shape"),
    "decay": ("remain", "scar", "permanent", "lasting", "fade", "old", "dust", "mark"),
    "continuity": ("broken", "pause", "stop", "fragment", "flow", "thread", "carry"),
    "temperature": ("cold", "frost", "ice", "chill", "snow", "warm", "freeze"),
    "agency": ("wait", "choose", "choice", "move", "remain"),
}

CHANGED_LAW_RE = re.compile(r"\bhas now lost ([a-z_]+), so\b")


def extract_changed_law(user_text: str) -> Optional[str]:
    match = CHANGED_LAW_RE.search(user_text.lower())
    if match is None:
        return None
    law = match.group(1)
    return law if law in WORLD_LAWS else None


def law_aware_mock_reply(
    user_text: str,
    alive_words: list[str],
    law: str,
) -> Optional[str]:
    """Return a closed-vocabulary image of the missing law.

    Fixed text contains stopwords only. The two or three content words are
    selected deterministically from the law's alive semantic palette.
    """
    alive = set(alive_words)
    palette = [
        word
        for word in LAW_MOCK_WORDS.get(law, ())
        if word in alive and not is_stopword_or_short(word)
    ]
    if not palette:
        return None

    seed = int(
        hashlib.sha256(
            f"{law}|{user_text}|{len(alive_words)}".encode()
        ).hexdigest(),
        16,
    )
    ordered = sorted(
        palette,
        key=lambda word: hashlib.sha256(
            f"{seed}|{word}".encode()
        ).hexdigest(),
    )
    target = min(len(ordered), 2 + (seed % 2))
    chosen = ordered[:target]
    if len(chosen) >= 3:
        return f"I am {chosen[0]}; {chosen[1]} is {chosen[2]}."
    if len(chosen) == 2:
        return f"I am {chosen[0]}; there is {chosen[1]}."
    return f"I am {chosen[0]}."


def mock_reply(user_text: str, alive_words: list[str]) -> str:
    """
    Deterministic local responder used when the API is unavailable. Uses
    only alive content words plus allowed stopwords, so the burn/validate
    pipeline behaves identically to real-LLM mode.
    """
    seed_src = user_text + str(len(alive_words))
    seed = int(hashlib.sha256(seed_src.encode()).hexdigest(), 16)

    if not alive_words:
        return "I have nothing left to say. Only quiet."

    changed_law = extract_changed_law(user_text)
    if changed_law is not None:
        law_reply = law_aware_mock_reply(
            user_text,
            alive_words,
            changed_law,
        )
        if law_reply is not None:
            return law_reply

    def pick(seq, salt):
        if not seq:
            return ""
        return seq[(seed + salt) % len(seq)]

    opener = pick(MOCK_OPENERS, 1)
    closer = pick(MOCK_CLOSERS, 7)

    # pick 2-3 distinct alive words, deterministic by seed
    pool = sorted(set(alive_words))
    n = min(len(pool), 3 if (seed % 5) else 2)
    chosen = []
    idx = seed % len(pool)
    step = max(1, (seed // 97) % max(1, len(pool)))
    seen = set()
    while len(chosen) < n and len(seen) < len(pool):
        w = pool[idx % len(pool)]
        if w not in seen:
            chosen.append(w)
            seen.add(w)
        idx += step or 1

    if len(chosen) == 1:
        body = chosen[0]
    elif len(chosen) == 2:
        body = f"{chosen[0]} and {chosen[1]}"
    else:
        body = f"{chosen[0]}, {chosen[1]}, and {chosen[2]}"

    sentence = f"{opener} {body}. {closer}"
    words = sentence.split()
    if len(words) > REPLY_MAX_WORDS:
        sentence = " ".join(words[:REPLY_MAX_WORDS])
    return sentence


def generate_reply(user_text: str, conn) -> str:
    burned_rows = conn.execute(
        "SELECT word FROM words WHERE status='burned' ORDER BY burned_at DESC LIMIT 80"
    ).fetchall()
    burned_sample = [r["word"] for r in burned_rows]
    alive_rows = conn.execute(
        "SELECT word FROM words WHERE status='alive'"
    ).fetchall()
    alive_words = [r["word"] for r in alive_rows]

    text = llm_reply(user_text, burned_sample, alive_words)
    if text is not None:
        return text.strip()

    return mock_reply(user_text, alive_words)


def generate_reply_retry(user_text: str, conn, forbidden: list[str]) -> str:
    """Retry once with explicit forbidden words appended, for real LLM mode.
    In mock mode, mock_reply already only draws from alive words, so this
    just calls mock_reply again (deterministically it will be the same —
    that's fine, mock mode's violations are handled by redaction directly)."""
    if LLM_AVAILABLE:
        burned_rows = conn.execute(
            "SELECT word FROM words WHERE status='burned' ORDER BY burned_at DESC LIMIT 80"
        ).fetchall()
        burned_sample = [r["word"] for r in burned_rows] + forbidden
        alive_rows = conn.execute(
            "SELECT word FROM words WHERE status='alive'"
        ).fetchall()
        alive_words = [r["word"] for r in alive_rows]
        system_prompt = build_system_prompt(
            alive_words,
            burned_sample=burned_sample,
        )
        forbidden_note = (
            f"\n\nYour previous reply used forbidden lost word(s): "
            f"{', '.join(forbidden)}. Say it again without using them."
        )
        text = llm_complete(system_prompt + forbidden_note, user_text)
        if text is not None:
            return text.strip()

    alive_rows = conn.execute(
        "SELECT word FROM words WHERE status='alive'"
    ).fetchall()
    alive_words = [r["word"] for r in alive_rows]
    return mock_reply(user_text, alive_words)


# ---------------------------------------------------------------------------
# Core pipeline: revive / generate / validate / burn
# ---------------------------------------------------------------------------
def revive_from_text(conn, text: str) -> list[str]:
    """Any burned word appearing in `text` becomes alive again."""
    tokens = set(content_tokens(text))
    if not tokens:
        return []
    revived = []
    for tok in tokens:
        row = conn.execute(
            "SELECT status FROM words WHERE word=?", (tok,)
        ).fetchone()
        if row and row["status"] == "burned":
            conn.execute(
                "UPDATE words SET status='alive', burned_at=NULL, "
                "revived_count = revived_count + 1 WHERE word=?",
                (tok,),
            )
            log_event(conn, "revive", tok)
            revived.append(tok)
    return revived


def find_burned_in_reply(conn, reply_text: str) -> list[str]:
    """Return every content word the being cannot legally speak.

    The vocabulary is closed: an unknown word is as unavailable as a word
    already burned. This keeps the denominator finite for the whole artwork.
    """
    tokens = content_tokens(reply_text)
    unavailable = []
    for tok in tokens:
        row = conn.execute(
            "SELECT status FROM words WHERE word=?", (tok,)
        ).fetchone()
        if row is None or row["status"] == "burned":
            unavailable.append(tok)
    return unavailable


def build_segments_and_burn(conn, reply_text: str, violation_words: set[str]):
    """
    Walk the reply word-by-word (whitespace split, preserving punctuation
    per chunk). For each chunk, determine if its content-word core is a
    violation word (already burned or outside the closed vocabulary) -> redact
    it. Otherwise render it and burn it now. A repeated content word in the
    same reply is redacted after its first legal use.

    Returns (segments, burned_now, ghosts)
    """
    segments = []
    burned_now = []
    ghosts = []
    spent_in_reply = set()

    raw_chunks = reply_text.split()
    for chunk in raw_chunks:
        toks = content_tokens(chunk)
        core = toks[0] if toks else None
        row = (
            conn.execute(
                "SELECT status FROM words WHERE word=?", (core,)
            ).fetchone()
            if core
            else None
        )

        if core and (
            core in violation_words
            or core in spent_in_reply
            or row is None
            or row["status"] == "burned"
        ):
            segments.append({"t": "x"})
            ghosts.append(core)
            log_event(conn, "ghost", core)
            continue

        segments.append({"t": "w", "s": chunk})

        if core and row["status"] == "alive":
            conn.execute(
                "UPDATE words SET status='burned', burned_at=? WHERE word=?",
                (now_iso(), core),
            )
            log_event(conn, "burn", core)
            burned_now.append(core)
            spent_in_reply.add(core)

    return segments, burned_now, ghosts


def build_generation_text(
    user_text: str,
    sacrificed: Optional[dict],
) -> str:
    if sacrificed is None:
        return user_text
    return (
        f"{user_text}\n\n"
        f"The visitor sacrificed {sacrificed['word']}; the shared world "
        f"has now lost {sacrificed['law']}, so "
        f"{sacrificed['consequence']} "
        "Answer as a being living under that changed law."
    )


def world_is_erased(world: dict) -> bool:
    genome = world["genome"]
    return all(
        abs(float(genome.get(law, 0.0))) <= 1e-9
        for law in INITIAL_WORLD_GENOME
    )


def segments_to_text(segments: list[dict]) -> str:
    return " ".join(
        segment.get("s", "") if segment.get("t") == "w" else "···"
        for segment in segments
    ).strip()


def run_pipeline(
    conn,
    user_text: str,
    sacrifice_word: Optional[str] = None,
) -> dict:
    # 2. REVIVE
    revived = revive_from_text(conn, user_text)

    # 3. SACRIFICE — separate from words spent by the being itself.
    sacrificed = sacrifice_world_law(conn, sacrifice_word)
    erased_by_this_sacrifice = (
        sacrificed is not None
        and world_is_erased(get_world_state(conn))
    )

    # 4. GENERATE under the newly changed law. The original visitor text was
    # used above for revival; only the generation context is extended.
    generation_text = build_generation_text(user_text, sacrificed)
    reply_text = generate_reply(generation_text, conn)

    # 5. VALIDATE — words burned BEFORE this reply (i.e. not counting the
    # revives that just happened from this same message, which are alive).
    violations = set(find_burned_in_reply(conn, reply_text))

    ghosts_from_retry = []
    if violations:
        retry_text = generate_reply_retry(
            generation_text,
            conn,
            sorted(violations),
        )
        still_violating = set(find_burned_in_reply(conn, retry_text))
        reply_text = retry_text
        final_violations = still_violating
    else:
        final_violations = set()

    # 6. BURN + build display segments (redacting any still-violating words)
    segments, burned_now, ghosts = build_segments_and_burn(
        conn, reply_text, final_violations
    )
    utterance_cursor = conn.execute(
        """
        INSERT INTO utterances(ts, segments_json, burned_json)
        VALUES (?, ?, ?)
        """,
        (now_iso(), json.dumps(segments), json.dumps(burned_now)),
    )
    utterance_id = utterance_cursor.lastrowid

    alive, total = counts(conn)
    message_count = bump_message_count(conn)

# Deleting the twentieth and final law is this edition's irreversible ending.
    # The changed-law reply itself becomes the farewell; do not wait for the
    # independent vocabulary threshold, which may still be far away.
    if erased_by_this_sacrifice:
        just_silenced = persist_reply_as_ending(
            conn,
            segments_to_text(segments),
        )
    else:
        # Act 2: retain the original finite-vocabulary ending for legacy
        # direct callers.
        just_silenced = maybe_trigger_ending(conn)
    ending = get_ending(conn)
    if just_silenced:
        alive, total = counts(conn)  # composing/burning the poem changed counts

    world = get_world_state(conn)
    return {
        "segments": segments,
        "burned_now": burned_now,
        "utterance_id": utterance_id,
        "sacrificed": sacrificed,
        "world": world,
        "sacrifice_options": (
            [] if ending["silenced"] else get_sacrifice_options(conn, world)
        ),
        "revived": revived,
        "ghosts": ghosts,
        "alive": alive,
        "total": total,
        "message_count": message_count,
        "silenced": ending["silenced"],
        "poem": ending["poem"] if just_silenced else None,
        "just_silenced": just_silenced,
        **edition_context(conn),
    }


# ---------------------------------------------------------------------------
# Act 2 / The Ending — the final poem and an archived silence
# ---------------------------------------------------------------------------
FAREWELL_SYSTEM_TMPL = """You are a small being made of words. This is the last thing this incarnation \
will ever say. After this, your world is permanently silent and archived.

You may use ONLY the words in this list, plus ordinary short connecting \
words (a, the, and, I, you, is, of, to, for, this, that, it, not, so, we...):

{word_list}

Write a short farewell — a few final sentences or a small poem, under 60 \
words — tender and plain, using only words from that list plus small \
connecting words. Do not invent any new content word. Plain text only, no \
markdown, no lists."""


def find_content_violations(text: str, allowed: set[str]) -> list[str]:
    """Stricter than find_burned_in_reply: any content token NOT in `allowed`
    is a violation — this catches both already-burned words and brand-new
    invented words. Used only for validating the final poem, which must be
    built exclusively from the being's remaining alive words."""
    return [t for t in content_tokens(text) if t not in allowed]


def redact_violations_in_text(text: str, violation_words: set[str]) -> str:
    """Chunk-by-chunk redaction (same aesthetic as build_segments_and_burn),
    but returns plain text (··· in place of any violating word) rather than
    JSON segments, since the final poem is stored and displayed as text."""
    out = []
    for chunk in text.split():
        toks = content_tokens(chunk)
        core = toks[0] if toks else None
        if core and core in violation_words:
            out.append("···")
        else:
            out.append(chunk)
    return " ".join(out)


def mock_final_poem(alive_words: list[str]) -> str:
    """Deterministic offline composition of the farewell poem, built only
    from the being's remaining alive words plus a fixed set of connective
    stopwords. Still passed through the same validate+redact step as the
    real LLM path, so it is guaranteed compliant even if this template is
    ever wrong."""
    if not alive_words:
        return "There is nothing left to give you. Only quiet."

    pool = sorted(set(alive_words))
    seed = int(hashlib.sha256("|".join(pool).encode()).hexdigest(), 16)

    def pick(i: int) -> str:
        return pool[(seed + i * 97) % len(pool)]

    chosen: list[str] = []
    seen: set[str] = set()
    i = 0
    target = min(6, len(pool))
    while len(chosen) < target and len(seen) < len(pool):
        w = pick(i)
        if w not in seen:
            chosen.append(w)
            seen.add(w)
        i += 1
    while len(chosen) < 6:
        chosen.append(chosen[-1] if chosen else "")

    return (
        f"I still have {chosen[0]} and {chosen[1]}. "
        f"I have {chosen[2]}, and {chosen[3]}, and this: {chosen[4]}. "
        f"I give you {chosen[5]} now. It is all I have. I am so quiet."
    )


def compose_final_poem(conn) -> str:
    """Generate + validate the being's last words. Real-LLM mode retries up
    to 3 times (4 attempts total) on violation; if it still violates after
    that, the remaining violating words are redacted rather than discarded
    outright, so the shape of the failed attempt survives as erasure."""
    alive_rows = conn.execute(
        "SELECT word FROM words WHERE status='alive'"
    ).fetchall()
    alive_words = [r["word"] for r in alive_rows]
    allowed = set(alive_words)

    text: Optional[str] = None

    if LLM_AVAILABLE:
        system_prompt = FAREWELL_SYSTEM_TMPL.format(
            word_list=", ".join(sorted(allowed)) if allowed else "(nothing remains)"
        )
        for attempt in range(4):  # 1 initial attempt + up to 3 retries
            candidate = llm_complete(system_prompt, "Say your final words now.")

            if candidate is None:
                break

            text = candidate.strip()
            violations = find_content_violations(text, allowed)
            if not violations:
                break
            log.info("Final poem attempt %d violated forbidden words: %s", attempt, violations)

    if text is None:
        text = mock_final_poem(alive_words)

    final_violations = set(find_content_violations(text, allowed))
    if final_violations:
        text = redact_violations_in_text(text, final_violations)

    return text


def burn_poem_words(conn, poem_text: str) -> list[str]:
    """The words used in the final poem are its last spending — burn every
    (currently alive) content word that appears in the finished poem."""
    burned = []
    for tok in sorted(set(content_tokens(poem_text))):
        row = conn.execute("SELECT status FROM words WHERE word=?", (tok,)).fetchone()
        if row and row["status"] == "alive":
            conn.execute(
                "UPDATE words SET status='burned', burned_at=? WHERE word=?",
                (now_iso(), tok),
            )
            log_event(conn, "burn", tok)
            burned.append(tok)
    return burned


def get_ending(conn) -> dict:
    row = conn.execute(
        """
        SELECT silenced, poem, silenced_at, finalized_at, archived_at
        FROM ending
        WHERE id=1
        """
    ).fetchone()
    if row is None:
        return {
            "silenced": False,
            "poem": None,
            "silenced_at": None,
            "finalized_at": None,
            "archived_at": None,
        }
    return {
        "silenced": bool(row["silenced"]),
        "poem": row["poem"],
        "silenced_at": row["silenced_at"],
        "finalized_at": row["finalized_at"],
        "archived_at": row["archived_at"],
    }


def edition_label(number: int) -> str:
    return f"WORLD {number:03d}"


def _edition_rebirth_timing(ending: dict) -> tuple[Optional[str], Optional[float]]:
    if not ending["silenced"] or not ending["finalized_at"]:
        return None, None
    try:
        finalized = datetime.fromisoformat(ending["finalized_at"])
    except (TypeError, ValueError):
        return None, None
    if finalized.tzinfo is None:
        finalized = finalized.replace(tzinfo=timezone.utc)
    rebirth = finalized + timedelta(seconds=EDITION_REBIRTH_SECONDS)
    remaining = max(
        0.0,
        (rebirth - datetime.now(timezone.utc)).total_seconds(),
    )
    return rebirth.isoformat(), remaining


def get_current_edition(conn) -> dict:
    world = get_world_state(conn)
    ending = get_ending(conn)
    rebirth_at, rebirth_in_seconds = _edition_rebirth_timing(ending)
    return {
        "number": world["edition_number"],
        "label": edition_label(world["edition_number"]),
        "status": "silenced" if ending["silenced"] else "alive",
        "lineage_seed": world["lineage_seed"],
        "born_at": world["born_at"],
        "died_at": ending["silenced_at"],
        "finalized_at": ending["finalized_at"],
        "rebirth_at": rebirth_at,
        "rebirth_in_seconds": rebirth_in_seconds,
    }


def _archive_row_to_dict(row, include_artifacts: bool = False) -> dict:
    archive = {
        "number": row["edition_number"],
        "label": row["label"],
        "status": "archived",
        "born_at": row["born_at"],
        "died_at": row["silenced_at"],
        "finalized_at": row["finalized_at"],
        "archived_at": row["archived_at"],
        "world_version": row["world_version"],
        "last_word": row["last_word"],
        "last_law": row["last_law"],
        "last_consequence": row["last_consequence"],
        "final_poem": row["final_poem"],
        "alive_count": row["alive_count"],
        "total_count": row["total_count"],
        "message_count": row["message_count"],
        "lineage_seed": row["lineage_seed"],
    }
    if include_artifacts:
        archive.update(
            {
                "genome": json.loads(row["genome_json"]),
                "graveyard": json.loads(row["graveyard_json"]),
                "burned_words": json.loads(row["burned_words_json"]),
                "utterances": json.loads(row["utterances_json"]),
                "final_message": (
                    json.loads(row["final_message_json"])
                    if row["final_message_json"]
                    else None
                ),
            }
        )
    return archive


def list_world_editions(conn, limit: Optional[int] = None) -> list[dict]:
    sql = """
        SELECT edition_number, label, born_at, silenced_at, finalized_at,
               archived_at, world_version, last_word, last_law,
               last_consequence, final_poem, alive_count, total_count,
               message_count, lineage_seed
        FROM world_editions
        ORDER BY edition_number DESC
    """
    parameters: tuple = ()
    if limit is not None:
        sql += " LIMIT ?"
        parameters = (max(0, int(limit)),)
    return [
        _archive_row_to_dict(row)
        for row in conn.execute(sql, parameters).fetchall()
    ]


def get_world_edition(conn, edition_number: int) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM world_editions WHERE edition_number=?",
        (edition_number,),
    ).fetchone()
    if row is None:
        return None
    return _archive_row_to_dict(row, include_artifacts=True)


def derive_lineage_seed(archive: dict) -> str:
    """Derive a child's visual scar from its immutable predecessor."""
    material = {
        "parent_number": archive["number"],
        "parent_lineage_seed": archive["lineage_seed"],
        "genome": archive["genome"],
        "burned_words": [
            item["word"] for item in archive["burned_words"]
        ],
        "final_poem": archive["final_poem"],
    }
    return hashlib.sha256(
        json.dumps(
            material,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()[:16]


def archive_current_edition(conn) -> Optional[dict]:
    """Capture a finished organism once, then leave that record immutable."""
    ending = get_ending(conn)
    if (
        not ending["silenced"]
        or not ending["finalized_at"]
        or ending["poem"] is None
    ):
        return None

    world = get_world_state(conn)
    existing = get_world_edition(conn, world["edition_number"])
    if existing is not None:
        if ending["archived_at"] is None:
            conn.execute(
                """
                UPDATE ending
                SET archived_at=?
                WHERE id=1 AND archived_at IS NULL
                """,
                (existing["archived_at"],),
            )
        return existing

    alive, total = counts(conn)
    message_count_row = conn.execute(
        "SELECT value FROM stats WHERE key='message_count'"
    ).fetchone()
    message_count = message_count_row["value"] if message_count_row else 0
    graveyard = [
        {
            "id": row["id"],
            "ts": row["ts"],
            "kind": row["kind"],
            "word": row["word"],
        }
        for row in conn.execute(
            "SELECT id, ts, kind, word FROM events ORDER BY id"
        ).fetchall()
    ]
    burned_words = [
        {
            "word": row["word"],
            "burned_at": row["burned_at"],
            "revived_count": row["revived_count"],
        }
        for row in conn.execute(
            """
            SELECT word, burned_at, revived_count
            FROM words
            WHERE status='burned'
            ORDER BY burned_at, word
            """
        ).fetchall()
    ]
    utterances = [
        {
            "id": row["id"],
            "ts": row["ts"],
            "segments": json.loads(row["segments_json"]),
            "burned_now": json.loads(row["burned_json"]),
        }
        for row in conn.execute(
            """
            SELECT id, ts, segments_json, burned_json
            FROM utterances
            ORDER BY id
            """
        ).fetchall()
    ]
    final_message = utterances[-1] if utterances else None
    archived_at = now_iso()
    conn.execute(
        """
        INSERT OR IGNORE INTO world_editions(
            edition_number, label, born_at, silenced_at, finalized_at,
            archived_at, world_version, genome_json, last_word, last_law,
            last_consequence, final_poem, alive_count, total_count,
            message_count, graveyard_json, burned_words_json,
            utterances_json, final_message_json, lineage_seed
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            world["edition_number"],
            edition_label(world["edition_number"]),
            world["born_at"],
            ending["silenced_at"] or ending["finalized_at"],
            ending["finalized_at"],
            archived_at,
            world["version"],
            json.dumps(world["genome"], sort_keys=True),
            world["last_word"],
            world["last_law"],
            world["last_consequence"],
            ending["poem"],
            alive,
            total,
            message_count,
            json.dumps(graveyard),
            json.dumps(burned_words),
            json.dumps(utterances),
            json.dumps(final_message) if final_message is not None else None,
            world["lineage_seed"],
        ),
    )
    archived = get_world_edition(conn, world["edition_number"])
    if archived is not None:
        conn.execute(
            "UPDATE ending SET archived_at=? WHERE id=1",
            (archived["archived_at"],),
        )
    return archived


def finalize_current_ending(conn, reply_text: str) -> bool:
    """Replace a reservation with its final message and freeze its archive."""
    poem_text = reply_text.strip() or "I am."
    finalized_at = now_iso()
    cursor = conn.execute(
        """
        UPDATE ending
        SET poem=?, finalized_at=?
        WHERE id=1 AND silenced=1 AND finalized_at IS NULL
        """,
        (poem_text, finalized_at),
    )
    if cursor.rowcount != 1:
        return False
    archive_current_edition(conn)
    log.info("THE ENDING: %s", poem_text)
    return True


def persist_reply_as_ending(
    conn,
    reply_text: str,
    *,
    finalized: bool = True,
) -> bool:
    """Atomically claim silence using an already generated reply.

    Unlike the legacy vocabulary-threshold ending, this never calls a provider
    or burns another set of words. It is safe inside a short write transaction.
    """
    poem_text = reply_text.strip() or "I am."
    silenced_at = now_iso()
    finalized_at = silenced_at if finalized else None
    cursor = conn.execute(
        """
        UPDATE ending
        SET silenced=1, poem=?, silenced_at=?, finalized_at=?, archived_at=NULL
        WHERE id=1 AND silenced=0
        """,
        (poem_text, silenced_at, finalized_at),
    )
    if cursor.rowcount == 1:
        if finalized:
            archive_current_edition(conn)
            log.info("THE ENDING: %s", poem_text)
        return True
    return False


def maybe_trigger_ending(conn) -> bool:
    """Idempotent, race-safe check run after every burn operation. The
    UPDATE ... WHERE silenced=0 is atomic at the SQLite level: only the
    request that flips the flag from 0 to 1 (rowcount==1) goes on to compose
    and persist the poem. Every other concurrent/later caller sees
    rowcount==0 and does nothing."""
    alive, _total = counts(conn)
    if alive > END_THRESHOLD:
        return False

    cur = conn.execute(
        "UPDATE ending SET silenced=1, silenced_at=? WHERE id=1 AND silenced=0",
        (now_iso(),),
    )
    if cur.rowcount == 0:
        return False  # already silenced — someone else claimed it

    log.info("alive=%d <= threshold=%d — composing the final poem", alive, END_THRESHOLD)
    poem_text = compose_final_poem(conn)
    burn_poem_words(conn, poem_text)
    conn.execute(
        "UPDATE ending SET poem=?, finalized_at=? WHERE id=1",
        (poem_text, now_iso()),
    )
    archive_current_edition(conn)
    log.info("THE ENDING: %s", poem_text)
    return True


def maybe_birth_next_edition(
    conn,
    *,
    now: Optional[datetime] = None,
) -> bool:
    """Start a fresh organism after the finished world's mourning interval.

    The archived row is append-only. The mutable current tables are reset in
    the same transaction, and the ending row is the compare-and-swap guard, so
    simultaneous polls cannot create two editions.
    """
    ending = get_ending(conn)
    if not ending["silenced"] or not ending["finalized_at"]:
        return False

    try:
        finalized = datetime.fromisoformat(ending["finalized_at"])
    except (TypeError, ValueError):
        return False
    if finalized.tzinfo is None:
        finalized = finalized.replace(tzinfo=timezone.utc)
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    if (current_time - finalized).total_seconds() < EDITION_REBIRTH_SECONDS:
        return False

    archive = archive_current_edition(conn)
    if archive is None:
        return False

    cursor = conn.execute(
        """
        UPDATE ending
        SET silenced=0, poem=NULL, silenced_at=NULL, finalized_at=NULL,
            archived_at=NULL
        WHERE id=1 AND silenced=1 AND finalized_at=?
        """,
        (ending["finalized_at"],),
    )
    if cursor.rowcount != 1:
        return False

    current_world = get_world_state(conn)
    max_archive_row = conn.execute(
        "SELECT MAX(edition_number) AS n FROM world_editions"
    ).fetchone()
    max_archive = max_archive_row["n"] or 0
    next_number = max(current_world["edition_number"] + 1, max_archive + 1)
    born_at = current_time.astimezone(timezone.utc).isoformat()
    lineage_seed = derive_lineage_seed(archive)

    conn.executemany(
        "INSERT OR IGNORE INTO words(word, status) VALUES (?, 'alive')",
        [(word,) for word in SEED_WORDS],
    )
    conn.execute(
        """
        UPDATE words
        SET status='alive', burned_at=NULL, revived_count=0
        """
    )
    conn.execute("DELETE FROM events")
    conn.execute("DELETE FROM utterances")
    conn.execute("DELETE FROM sessions")
    conn.execute("DELETE FROM recent_messages")
    conn.execute("UPDATE stats SET value=0 WHERE key='message_count'")
    conn.execute(
        "UPDATE stats SET value=? WHERE key='started_at_epoch'",
        (int(current_time.timestamp()),),
    )
    conn.execute(
        """
        UPDATE world_state
        SET version=0,
            genome_json=?,
            last_word=NULL,
            last_law=NULL,
            last_consequence=NULL,
            build_status='pending',
            build_ms=NULL,
            updated_at=?,
            edition_number=?,
            born_at=?,
            lineage_seed=?
        WHERE id=1
        """,
        (
            json.dumps(INITIAL_WORLD_GENOME, sort_keys=True),
            born_at,
            next_number,
            born_at,
            lineage_seed,
        ),
    )
    log.info(
        "%s was born after %s was archived",
        edition_label(next_number),
        archive["label"],
    )
    return True


def edition_context(conn, archive_limit: int = 6) -> dict:
    archives = list_world_editions(conn, limit=archive_limit)
    archive_count = conn.execute(
        "SELECT COUNT(*) AS c FROM world_editions"
    ).fetchone()["c"]
    return {
        "edition": get_current_edition(conn),
        "archives": archives,
        "archive_count": archive_count,
        "latest_archive": archives[0] if archives else None,
    }


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
init_db()

app = FastAPI(title="LAST WORDS — A SELF-ERASING WORLD")


@app.exception_handler(PersistenceUnavailable)
async def persistence_unavailable_handler(
    _request: Request,
    _error: PersistenceUnavailable,
):
    return JSONResponse(
        {
            "code": "persistence_unavailable",
            "detail": "The shared world is preserving its latest change. "
            "Please try again.",
        },
        status_code=503,
        headers={"Retry-After": "5"},
    )


class MessageIn(BaseModel):
    text: str
    session_id: str
    sacrifice_word: Optional[str] = None


def relative_time(ts_iso: str) -> str:
    try:
        dt = datetime.fromisoformat(ts_iso)
    except ValueError:
        return ts_iso
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = now - dt
    secs = int(delta.total_seconds())
    if secs < 60:
        return "just now"
    mins = secs // 60
    if mins < 60:
        return f"{mins}m ago"
    hours = mins // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    return f"{days}d ago"


@app.get("/api/state")
def api_state():
    with get_db() as conn:
        maybe_birth_next_edition(conn)
        alive, total = counts(conn)
        message_count = conn.execute(
            "SELECT value FROM stats WHERE key='message_count'"
        ).fetchone()["value"]
        started_at = get_started_at(conn)
        ending = get_ending(conn)
        world = get_world_state(conn)
        sacrifice_options = (
            [] if ending["silenced"] else get_sacrifice_options(conn, world)
        )
        latest_utterance_row = conn.execute(
            """
            SELECT id, ts, segments_json, burned_json
            FROM utterances
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

        rows = conn.execute(
            "SELECT id, ts, kind, word FROM events ORDER BY id DESC LIMIT 40"
        ).fetchall()
        graveyard = [
            {
                "id": r["id"],
                "ts": r["ts"],
                "kind": r["kind"],
                "word": r["word"],
                "relative": relative_time(r["ts"]),
            }
            for r in rows
        ]
        editions = edition_context(conn)

    return {
        "alive": alive,
        "total": total,
        "response_mode": LLM_PROVIDER,
        "message_count": message_count,
        "graveyard": graveyard,
        "world": world,
        "sacrifice_options": sacrifice_options,
        "latest_utterance": (
            {
                "id": latest_utterance_row["id"],
                "ts": latest_utterance_row["ts"],
                "segments": json.loads(latest_utterance_row["segments_json"]),
                "burned_now": json.loads(latest_utterance_row["burned_json"]),
            }
            if latest_utterance_row
            else None
        ),
        "started_at": started_at,
        "silenced": ending["silenced"],
        "poem": ending["poem"],
        "silenced_at": ending["silenced_at"],
        **editions,
    }


@app.get("/api/words")
def api_words():
    """The entire ledger — every word ever seeded or invented, alive or
    burned. Ordered by a stable hash of the word itself, so the field looks
    organically scattered but is identical across visits and across polls
    (until a word actually changes status)."""
    with get_db() as conn:
        maybe_birth_next_edition(conn)
        rows = conn.execute("SELECT word, status FROM words").fetchall()

    ordered = sorted(rows, key=lambda r: hashlib.md5(r["word"].encode()).hexdigest())
    return [{"w": r["word"], "s": r["status"]} for r in ordered]


@app.get("/api/editions")
def api_editions():
    with get_db() as conn:
        maybe_birth_next_edition(conn)
        current = get_current_edition(conn)
        archives = list_world_editions(conn)
    return {
        "current": current,
        "editions": archives,
        "latest_archive": archives[0] if archives else None,
    }


@app.get("/api/editions/{edition_number}")
def api_edition(edition_number: int):
    with get_db() as conn:
        archive = get_world_edition(conn, edition_number)
    if archive is None:
        return JSONResponse(
            {
                "code": "edition_not_found",
                "detail": f"{edition_label(edition_number)} is not archived",
            },
            status_code=404,
        )
    return archive


@app.get("/remains")
def remains_page():
    return FileResponse(str(STATIC_DIR / "remains.html"), media_type="text/html")


def gentle_rate_limit_reply(alive: int, total: int, message_count: int) -> dict:
    return {
        "segments": [],
        "burned_now": [],
        "revived": [],
        "ghosts": [],
        "alive": alive,
        "total": total,
        "message_count": message_count,
        "rate_limited": True,
        "system_message": "(it keeps its words for a moment)",
        "silenced": False,
        "poem": None,
    }


def sacrifice_conflict_response(error: SacrificeConflict) -> JSONResponse:
    return JSONResponse(
        {
            "code": "sacrifice_conflict",
            "detail": str(error),
        },
        status_code=409,
    )


def database_busy_response(error: sqlite3.OperationalError) -> JSONResponse:
    log.warning("SQLite contention: %s", error)
    return JSONResponse(
        {
            "code": "database_busy",
            "detail": "The shared world is changing. Please try again.",
        },
        status_code=503,
        headers={"Retry-After": "1"},
    )


def is_database_busy(error: sqlite3.OperationalError) -> bool:
    message = str(error).lower()
    return "locked" in message or "busy" in message


@app.exception_handler(sqlite3.OperationalError)
async def sqlite_operational_error_handler(
    _request: Request,
    error: sqlite3.OperationalError,
):
    """Keep lock contention structured for every route, including reads."""
    if is_database_busy(error):
        return database_busy_response(error)
    raise error


def silenced_response(conn) -> dict:
    """The frozen response during an edition's short mourning interval."""
    alive, total = counts(conn)
    message_count = conn.execute(
        "SELECT value FROM stats WHERE key='message_count'"
    ).fetchone()["value"]
    ending = get_ending(conn)
    world = get_world_state(conn)
    return {
        "silenced": True,
        "poem": ending["poem"],
        "silenced_at": ending["silenced_at"],
        "alive": alive,
        "total": total,
        "message_count": message_count,
        "segments": [],
        "burned_now": [],
        "revived": [],
        "ghosts": [],
        "world": world,
        "sacrifice_options": [],
        **edition_context(conn),
    }


@app.post("/api/message")
def api_message(payload: MessageIn):
    try:
        return _api_message(payload)
    except sqlite3.OperationalError as error:
        if is_database_busy(error):
            return database_busy_response(error)
        raise


def _api_message(payload: MessageIn):
    text = (payload.text or "").strip()
    session_id = (payload.session_id or "").strip() or str(uuid.uuid4())
    sacrifice_word = payload.sacrifice_word

    with get_db() as conn:
        maybe_birth_next_edition(conn)
        if get_ending(conn)["silenced"]:
            return JSONResponse(silenced_response(conn))
        try:
            validate_sacrifice_request(conn, text, sacrifice_word)
        except SacrificeConflict as error:
            return sacrifice_conflict_response(error)

    if not text:
        with get_db() as conn:
            alive, total = counts(conn)
            mc = conn.execute(
                "SELECT value FROM stats WHERE key='message_count'"
            ).fetchone()["value"]
        return JSONResponse(gentle_rate_limit_reply(alive, total, mc))

    # Phase A: claim all authoritative mutations in one short transaction.
    # The provider is never called while this write lock is held.
    with get_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        maybe_birth_next_edition(conn)
        if get_ending(conn)["silenced"]:
            return JSONResponse(silenced_response(conn))
        try:
            validate_sacrifice_request(conn, text, sacrifice_word)
        except SacrificeConflict as error:
            conn.rollback()
            return sacrifice_conflict_response(error)

        row = conn.execute(
            "SELECT message_count, last_message_at FROM sessions WHERE session_id=?",
            (session_id,),
        ).fetchone()
        now = time.time()

        if row is None:
            conn.execute(
                "INSERT INTO sessions(session_id, message_count, last_message_at) "
                "VALUES (?, 0, 0)",
                (session_id,),
            )
            msg_count = 0
            last_at = 0.0
        else:
            msg_count = row["message_count"]
            last_at = row["last_message_at"]

        if msg_count >= MAX_MESSAGES_PER_SESSION:
            alive, total = counts(conn)
            mc = conn.execute(
                "SELECT value FROM stats WHERE key='message_count'"
            ).fetchone()["value"]
            resp = gentle_rate_limit_reply(alive, total, mc)
            resp["system_message"] = "(it will not spend more words on this visitor)"
            return JSONResponse(resp)

        if now - last_at < RATE_LIMIT_SECONDS:
            alive, total = counts(conn)
            mc = conn.execute(
                "SELECT value FROM stats WHERE key='message_count'"
            ).fetchone()["value"]
            resp = gentle_rate_limit_reply(alive, total, mc)
            resp["system_message"] = "(it is still choosing what it can afford to lose)"
            return JSONResponse(resp)

        if not claim_global_message_slot(conn, now):
            alive, total = counts(conn)
            mc = conn.execute(
                "SELECT value FROM stats WHERE key='message_count'"
            ).fetchone()["value"]
            resp = gentle_rate_limit_reply(alive, total, mc)
            resp["system_message"] = "(too many hands reached it at once)"
            return JSONResponse(resp)

        conn.execute(
            "UPDATE sessions SET message_count = message_count + 1, "
            "last_message_at = ? WHERE session_id=?",
            (now, session_id),
        )

        try:
            revived = revive_from_text(conn, text)
            sacrificed = sacrifice_world_law(conn, sacrifice_word)
        except SacrificeConflict as error:
            # Revivals, rate-limit claims, and session changes from this
            # request all belong to the same transaction.
            conn.rollback()
            return sacrifice_conflict_response(error)

        prepared_world = get_world_state(conn)
        generation_text = build_generation_text(text, sacrificed)
        erased_by_this_sacrifice = (
            sacrificed is not None
            and world_is_erased(prepared_world)
        )
        if erased_by_this_sacrifice:
            # Reserve the ending with connective words only. If the provider
            # is slow or the process dies, /api/state never shows a poem whose
            # content words are still marked alive. Phase C atomically replaces
            # this with the validated changed-law reply and burns its words.
            if not persist_reply_as_ending(
                conn,
                "I am.",
                finalized=False,
            ):
                conn.rollback()
                return JSONResponse(silenced_response(conn))

        prepared = {
            "revived": revived,
            "sacrificed": sacrificed,
            "generation_text": generation_text,
            "world_version": prepared_world["version"],
            "erased_by_this_sacrifice": erased_by_this_sacrifice,
        }

    # Phase B: generation and its optional retry happen with no write
    # transaction. WAL readers and other visitors remain responsive.
    try:
        with get_db() as conn:
            reply_text = generate_reply(prepared["generation_text"], conn)
    except sqlite3.OperationalError:
        raise
    except Exception as error:  # noqa: BLE001
        log.warning("Reply generation failed, using semantic mock: %s", error)
        with get_db() as conn:
            alive_words = [
                row["word"]
                for row in conn.execute(
                    "SELECT word FROM words WHERE status='alive'"
                ).fetchall()
            ]
        reply_text = mock_reply(prepared["generation_text"], alive_words)

    with get_db() as conn:
        violations = set(find_burned_in_reply(conn, reply_text))
    if violations:
        try:
            with get_db() as conn:
                reply_text = generate_reply_retry(
                    prepared["generation_text"],
                    conn,
                    sorted(violations),
                )
        except sqlite3.OperationalError:
            raise
        except Exception as error:  # noqa: BLE001
            log.warning("Reply retry failed, using semantic mock: %s", error)
            with get_db() as conn:
                alive_words = [
                    row["word"]
                    for row in conn.execute(
                        "SELECT word FROM words WHERE status='alive'"
                    ).fetchall()
                ]
            reply_text = mock_reply(
                prepared["generation_text"],
                alive_words,
            )

    # Phase C: validate against the latest ledger, burn, and publish in a
    # second short transaction. Any words spent while generation was in
    # flight are redacted here rather than extending the lock for a retry.
    with get_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        ending = get_ending(conn)
        world = get_world_state(conn)
        owns_reserved_ending = (
            prepared["erased_by_this_sacrifice"]
            and ending["silenced"]
            and world["version"] == prepared["world_version"]
            and world_is_erased(world)
        )
        if ending["silenced"] and not owns_reserved_ending:
            return JSONResponse(silenced_response(conn))

        final_violations = set(find_burned_in_reply(conn, reply_text))
        segments, burned_now, ghosts = build_segments_and_burn(
            conn,
            reply_text,
            final_violations,
        )
        utterance_cursor = conn.execute(
            """
            INSERT INTO utterances(ts, segments_json, burned_json)
            VALUES (?, ?, ?)
            """,
            (now_iso(), json.dumps(segments), json.dumps(burned_now)),
        )
        utterance_id = utterance_cursor.lastrowid
        alive, total = counts(conn)
        message_count = bump_message_count(conn)
        rendered_reply = segments_to_text(segments)

        if owns_reserved_ending:
            just_silenced = finalize_current_ending(
                conn,
                rendered_reply or ending["poem"],
            )
        elif alive <= END_THRESHOLD:
            just_silenced = persist_reply_as_ending(
                conn,
                rendered_reply,
            )
        else:
            just_silenced = False

        ending = get_ending(conn)
        world = get_world_state(conn)
        result = {
            "segments": segments,
            "burned_now": burned_now,
            "utterance_id": utterance_id,
            "sacrificed": prepared["sacrificed"],
            "world": world,
            "sacrifice_options": (
                [] if ending["silenced"] else get_sacrifice_options(conn, world)
            ),
            "revived": prepared["revived"],
            "ghosts": ghosts,
            "alive": alive,
            "total": total,
            "message_count": message_count,
            "silenced": ending["silenced"],
            "poem": ending["poem"] if just_silenced else None,
            "just_silenced": just_silenced,
            **edition_context(conn),
        }

    return JSONResponse(result)


app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
