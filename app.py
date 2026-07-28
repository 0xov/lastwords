"""
LAST WORDS — app.py

A being whose vocabulary is a finite, globally shared resource. Every
content word it speaks is burned forever, for every visitor, everywhere.
The only way a word returns is if a visitor uses it first.

This file contains: DB init/schema, tokenizer, LLM call (+ mock fallback),
the burn/revive/validate pipeline, and the FastAPI routes.

Run:
    uvicorn app:app --port 8787

Env:
    ANTHROPIC_API_KEY   if unset (or the API call fails), falls back to
                        deterministic mock mode. The mechanic is identical
                        in both modes.
"""

import hashlib
import json
import logging
import os
import re
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from seed_words import SEED_WORDS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("lastwords")

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("LASTWORDS_DB", BASE_DIR / "lastwords.db"))
STATIC_DIR = BASE_DIR / "static"

MAX_MESSAGES_PER_SESSION = 20
RATE_LIMIT_SECONDS = 3
REPLY_MAX_WORDS = 50

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
# Database
# ---------------------------------------------------------------------------
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
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
            CREATE TABLE IF NOT EXISTS ending (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                silenced INTEGER NOT NULL DEFAULT 0,
                poem TEXT,
                silenced_at TEXT
            )
            """
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
        conn.execute("INSERT OR IGNORE INTO ending(id, silenced) VALUES (1, 0)")


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


# ---------------------------------------------------------------------------
# LLM integration (Gemini REST or Anthropic SDK, with deterministic mock
# fallback). Provider priority: GEMINI_API_KEY > ANTHROPIC_API_KEY > mock.
# ---------------------------------------------------------------------------
MODEL_ID = "claude-sonnet-5"
GEMINI_MODEL = os.environ.get("LASTWORDS_MODEL", "gemini-2.5-flash")

LLM_PROVIDER = "mock"
_client = None
if os.environ.get("GEMINI_API_KEY"):
    LLM_PROVIDER = "gemini"
    log.info("LLM mode: GEMINI (model=%s)", GEMINI_MODEL)
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


def llm_complete(system_prompt: str, user_text: str) -> Optional[str]:
    """One completion from whichever real provider is configured.
    Returns None on any failure (or in mock mode) so callers fall back."""
    try:
        if LLM_PROVIDER == "gemini":
            return _gemini_complete(system_prompt, user_text)
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


def build_system_prompt(alive_sample_size: int = 0, burned_sample: Optional[list[str]] = None) -> str:
    burned_sample = burned_sample or []
    burned_list = ", ".join(burned_sample) if burned_sample else "(none yet — nothing has been lost)"
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

If you cannot say something without one of these lost words, approximate
with a word you still have, or leave a small gap, or say it more simply.
Do not apologize at length for this — it is just how you are now.

Reply in plain text only, under 50 words, in English. No markdown, no lists."""


def llm_reply(user_text: str, burned_sample: list[str]) -> Optional[str]:
    """Call the real API. Returns None on any failure so caller can fall back."""
    if not LLM_AVAILABLE:
        return None
    return llm_complete(build_system_prompt(burned_sample=burned_sample), user_text)


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


def mock_reply(user_text: str, alive_words: list[str]) -> str:
    """
    Deterministic local responder used when the API is unavailable. Uses
    only alive content words plus allowed stopwords, so the burn/validate
    pipeline behaves identically to real-LLM mode.
    """
    import hashlib

    seed_src = user_text + str(len(alive_words))
    seed = int(hashlib.sha256(seed_src.encode()).hexdigest(), 16)

    if not alive_words:
        return "I have nothing left to say. Only quiet."

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

    text = llm_reply(user_text, burned_sample)
    if text is not None:
        return text.strip()

    alive_rows = conn.execute(
        "SELECT word FROM words WHERE status='alive'"
    ).fetchall()
    alive_words = [r["word"] for r in alive_rows]
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
        system_prompt = build_system_prompt(burned_sample=burned_sample)
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
    tokens = content_tokens(reply_text)
    burned = []
    for tok in tokens:
        row = conn.execute(
            "SELECT status FROM words WHERE word=?", (tok,)
        ).fetchone()
        if row and row["status"] == "burned":
            burned.append(tok)
    return burned


def build_segments_and_burn(conn, reply_text: str, violation_words: set[str]):
    """
    Walk the reply word-by-word (whitespace split, preserving punctuation
    per chunk). For each chunk, determine if its content-word core is a
    violation word (already burned before this reply) -> redact it.
    Otherwise render it, and if it's a content word: burn it now (or insert
    as burned if brand new).

    Returns (segments, burned_now, ghosts)
    """
    segments = []
    burned_now = []
    ghosts = []

    raw_chunks = reply_text.split()
    for chunk in raw_chunks:
        toks = content_tokens(chunk)
        core = toks[0] if toks else None

        if core and core in violation_words:
            segments.append({"t": "x"})
            ghosts.append(core)
            log_event(conn, "ghost", core)
            continue

        segments.append({"t": "w", "s": chunk})

        if core:
            row = conn.execute(
                "SELECT status FROM words WHERE word=?", (core,)
            ).fetchone()
            if row is None:
                # New word the being invented — it appears already spent.
                conn.execute(
                    "INSERT INTO words(word, status, burned_at) VALUES (?, 'burned', ?)",
                    (core, now_iso()),
                )
                log_event(conn, "burn", core)
                burned_now.append(core)
            elif row["status"] == "alive":
                conn.execute(
                    "UPDATE words SET status='burned', burned_at=? WHERE word=?",
                    (now_iso(), core),
                )
                log_event(conn, "burn", core)
                burned_now.append(core)
            # if already burned and not in violation_words -> shouldn't
            # happen (would've been caught above), but guard anyway: skip.

    return segments, burned_now, ghosts


def run_pipeline(conn, user_text: str) -> dict:
    # 2. REVIVE
    revived = revive_from_text(conn, user_text)

    # 3. GENERATE
    reply_text = generate_reply(user_text, conn)

    # 4. VALIDATE — words burned BEFORE this reply (i.e. not counting the
    # revives that just happened from this same message, which are alive).
    violations = set(find_burned_in_reply(conn, reply_text))

    ghosts_from_retry = []
    if violations:
        retry_text = generate_reply_retry(user_text, conn, sorted(violations))
        still_violating = set(find_burned_in_reply(conn, retry_text))
        reply_text = retry_text
        final_violations = still_violating
    else:
        final_violations = set()

    # 5. BURN + build display segments (redacting any still-violating words)
    segments, burned_now, ghosts = build_segments_and_burn(
        conn, reply_text, final_violations
    )

    alive, total = counts(conn)
    message_count = bump_message_count(conn)

    # Act 2: check, after every burn, whether the pool has run dry enough
    # that this was (or already was) the being's last spendable breath.
    just_silenced = maybe_trigger_ending(conn)
    ending = get_ending(conn)
    if just_silenced:
        alive, total = counts(conn)  # composing/burning the poem changed counts

    return {
        "segments": segments,
        "burned_now": burned_now,
        "revived": revived,
        "ghosts": ghosts,
        "alive": alive,
        "total": total,
        "message_count": message_count,
        "silenced": ending["silenced"],
        "poem": ending["poem"] if just_silenced else None,
        "just_silenced": just_silenced,
    }


# ---------------------------------------------------------------------------
# Act 2 / The Ending — the final poem and permanent silence
# ---------------------------------------------------------------------------
FAREWELL_SYSTEM_TMPL = """You are a small being made of words. This is the last thing you will ever \
say. After this, you fall permanently silent — no more words, ever, for anyone.

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
    but returns plain text (▓▓▓ in place of any violating word) rather than
    JSON segments, since the final poem is stored and displayed as text."""
    out = []
    for chunk in text.split():
        toks = content_tokens(chunk)
        core = toks[0] if toks else None
        if core and core in violation_words:
            out.append("▓▓▓")
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
        "SELECT silenced, poem, silenced_at FROM ending WHERE id=1"
    ).fetchone()
    if row is None:
        return {"silenced": False, "poem": None, "silenced_at": None}
    return {
        "silenced": bool(row["silenced"]),
        "poem": row["poem"],
        "silenced_at": row["silenced_at"],
    }


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
    conn.execute("UPDATE ending SET poem=? WHERE id=1", (poem_text,))
    log.info("THE ENDING: %s", poem_text)
    return True


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
init_db()

app = FastAPI(title="LAST WORDS")


class MessageIn(BaseModel):
    text: str
    session_id: str


class GreetIn(BaseModel):
    session_id: str


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
        alive, total = counts(conn)
        message_count = conn.execute(
            "SELECT value FROM stats WHERE key='message_count'"
        ).fetchone()["value"]
        started_at = get_started_at(conn)
        ending = get_ending(conn)

        rows = conn.execute(
            "SELECT ts, kind, word FROM events ORDER BY id DESC LIMIT 40"
        ).fetchall()
        graveyard = [
            {
                "ts": r["ts"],
                "kind": r["kind"],
                "word": r["word"],
                "relative": relative_time(r["ts"]),
            }
            for r in rows
        ]

    return {
        "alive": alive,
        "total": total,
        "message_count": message_count,
        "graveyard": graveyard,
        "started_at": started_at,
        "silenced": ending["silenced"],
        "poem": ending["poem"],
        "silenced_at": ending["silenced_at"],
    }


@app.get("/api/words")
def api_words():
    """The entire ledger — every word ever seeded or invented, alive or
    burned. Ordered by a stable hash of the word itself, so the field looks
    organically scattered but is identical across visits and across polls
    (until a word actually changes status)."""
    with get_db() as conn:
        rows = conn.execute("SELECT word, status FROM words").fetchall()

    ordered = sorted(rows, key=lambda r: hashlib.md5(r["word"].encode()).hexdigest())
    return [{"w": r["word"], "s": r["status"]} for r in ordered]


@app.get("/remains")
def remains_page():
    return FileResponse(str(STATIC_DIR / "remains.html"), media_type="text/html")


def gentle_rate_limit_reply(alive: int, total: int, message_count: int) -> dict:
    return {
        "segments": [
            {"t": "w", "s": "..."},
        ],
        "burned_now": [],
        "revived": [],
        "ghosts": [],
        "alive": alive,
        "total": total,
        "message_count": message_count,
        "rate_limited": True,
        "silenced": False,
        "poem": None,
    }


def silenced_response(conn) -> dict:
    """The frozen response every visitor gets once the being has spoken its
    last words: nothing changes, ever again."""
    alive, total = counts(conn)
    message_count = conn.execute(
        "SELECT value FROM stats WHERE key='message_count'"
    ).fetchone()["value"]
    ending = get_ending(conn)
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
    }


@app.post("/api/message")
def api_message(payload: MessageIn):
    text = (payload.text or "").strip()
    session_id = (payload.session_id or "").strip() or str(uuid.uuid4())

    with get_db() as conn:
        if get_ending(conn)["silenced"]:
            return JSONResponse(silenced_response(conn))

    if not text:
        with get_db() as conn:
            alive, total = counts(conn)
            mc = conn.execute(
                "SELECT value FROM stats WHERE key='message_count'"
            ).fetchone()["value"]
        return JSONResponse(gentle_rate_limit_reply(alive, total, mc))

    with get_db() as conn:
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
            resp["segments"] = [
                {"t": "w", "s": "I"}, {"t": "w", "s": "have"},
                {"t": "w", "s": "said"}, {"t": "w", "s": "enough"},
                {"t": "w", "s": "to"}, {"t": "w", "s": "you"},
                {"t": "w", "s": "for"}, {"t": "w", "s": "now."},
            ]
            return JSONResponse(resp)

        if now - last_at < RATE_LIMIT_SECONDS:
            alive, total = counts(conn)
            mc = conn.execute(
                "SELECT value FROM stats WHERE key='message_count'"
            ).fetchone()["value"]
            resp = gentle_rate_limit_reply(alive, total, mc)
            resp["segments"] = [
                {"t": "w", "s": "...give"}, {"t": "w", "s": "me"},
                {"t": "w", "s": "a"}, {"t": "w", "s": "moment..."},
            ]
            return JSONResponse(resp)

        conn.execute(
            "UPDATE sessions SET message_count = message_count + 1, "
            "last_message_at = ? WHERE session_id=?",
            (now, session_id),
        )

        result = run_pipeline(conn, text)

    return JSONResponse(result)


@app.post("/api/greet")
def api_greet(payload: GreetIn):
    """Server generates a short greeting per visitor. Same burn pipeline
    applies — the greeting costs the being words too."""
    with get_db() as conn:
        if get_ending(conn)["silenced"]:
            return JSONResponse(silenced_response(conn))

        greeting_prompt = (
            "Greet a new visitor who has just arrived. Keep it very short — "
            "one sentence."
        )
        result = run_pipeline(conn, greeting_prompt)
    return JSONResponse(result)


app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
