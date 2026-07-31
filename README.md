# LAST WORDS

An interactive net-art piece for Hack the Arts.

## Concept

LAST WORDS is a shared, self-erasing world. Its AI being has a finite
vocabulary, and each offered word carries one executable law of its visible
body: gravity, memory, attraction, turbulence, light, symmetry, touch, and
more. Before the being may answer, a visitor must choose one living word to
sacrifice. The server burns that word, removes the law it carried from the
shared world genome, and tells the AI to answer as a being now living under
that absence.

The browser does not play a prepared transition. It inserts the new genome
into the artwork's GLSL fragment shader and actually compiles a new world.
Hovering or focusing a possible sacrifice previews the altered physics through
uniforms without committing it; submitting makes the deletion permanent,
increments the shared build number, and causes every open visitor to compile
the same mutation on the next 2.5-second state sync.

The AI also loses every content word it uses in its answer. Its vocabulary is
a single finite pool shared by every visitor. When it burns a word, that word
is gone from the being's mouth for everyone — the next visitor meets both a
poorer language and a physically different world.

There is exactly one way a lost word returns: a visitor has to type it back.
If you say "ocean" to the being, and "ocean" had been burned, it comes back
alive. This is the only mechanic of care the piece offers, and it is
irreversible in the other direction — the being cannot decide to keep a word
for itself. It can only spend and hope.

The piece has a scripted death. Its shared body begins with 20 executable
laws; the answer produced after the twentieth and final sacrifice becomes
its farewell. That world falls permanently silent, is frozen as a numbered
read-only edition, and is never reset or overwritten. After a short mourning
interval, a new world is born with restored capacity but a unique lineage
seed derived from the parent archive's actual genome, burned words, and final
poem. A low-vocabulary threshold remains as a safety ending if language runs
out first. See [Act 2 / The Ending](#act-2--the-ending) below.

**This piece cannot exist without technology.** SQLite is the shared memory
that makes every deletion real for every visitor; an atomic transaction
prevents two people from sacrificing the same law; an LLM improvises under
the world's newly missing physics; server-side validation enforces the finite
language; and WebGL recompiles the body visitors have collectively damaged.
The audience is not choosing among prerecorded scenes. It is changing the
executable conditions that produce the next scene.

## How the loop works

```
visitor previews a living word, chooses it, and asks a question
        │
        ▼
 [1] PREFLIGHT      word is still alive and its law still exists?
        │
        ▼
 [2] CLAIM          a short BEGIN IMMEDIATE transaction claims the session,
        │            revivals, sacrifice, and new shared genome version
        ▼
 [3] REVIVE         burned words typed by the visitor return
        │
        ▼
 [4] SACRIFICE      chosen word burns; its genome parameter becomes zero;
        │             shared build version increments; the lock is released
        ▼
 [5] GENERATE       outside the write lock, the LLM answers under the
        │             newly missing law
        │
        ▼
 [6] VALIDATE       burned, unknown, or repeated content words are violations
        │
        ├─ no violations ──────────────────────────────┐
        │                                                │
        └─ violations found → retry ONCE with those      │
           words explicitly forbidden                    │
                    │                                     │
                    ├─ retry is clean ──────────────────┤
                    │                                     │
                    └─ retry still violates → keep the    │
                       retry text, but redact each         │
                       violating occurrence as ···          │
                       (logged as a 'ghost' event)          │
                                                             ▼
 [7] COMMIT         a second short transaction rechecks the current ledger
        │             and burns every displayed, non-redacted content word:
        │            - alive in the pool → mark burned, timestamp it
        │            - unknown → never inserted; render only an absence
        │            (each logged as a 'burn' event)
        ▼
 [8] RESPOND        words + changed genome + three new sacrifice options
        │
        ▼
 [9] RECOMPILE      browser bakes the genome into GLSL and compiles the
                      next visible world; all other visitors follow by poll
```

`GET /api/state` returns the current alive/total counts, the latest persisted
utterance, the world genome/build version, three valid sacrifice options, and
the last 40 burn/ghost/revive events. The frontend polls it every 2.5 seconds,
so one visitor's missing law visibly propagates to everyone else.

## Act 2 / The Ending

Two additions on top of the base mechanic.

### THE REMAINS — `/remains`

A second page: the entire vocabulary — all ~1,160 words, alive and burned —
rendered as one flowing field, `GET /api/words` → `[{w, s}]`. Alive words
render as normal text. Burned words render as solid blackout bars, sized to
the word's length but carrying no text anywhere in the DOM — not in
`textContent`, not in a `data-*` attribute, nothing. The word's letters exist
only for the instant the client uses `word.length` to size the bar, then
they're gone from that response entirely. It reads as erasure poetry: a
field of ordinary words with growing black rectangles where words used to
be. The word order itself is neither alphabetical nor request-random — it's
sorted by a stable hash of each word, so the field looks organically
scattered but is bit-for-bit identical across visits and across polls, until
a word's status actually changes. The page polls `/api/words` every 2.5s and
diffs against what it already rendered, so a word transitioning to burned
gets a brief ember-colored fade before settling into its bar — you can watch
someone else's conversation erase a word from the field in near-real time.

### The twentieth law, the final poem, and the next world

The primary ending is structural, not a distant word-count timer. There are
20 executable laws in the shared genome. When a visitor sacrifices the last
one, that twentieth changed-law answer becomes the being's farewell and the
current world falls permanently silent. The first short transaction immediately
reserves the ending with the content-word-free fallback `I am.`; generation
then runs outside the write lock; the second short transaction validates and
burns the finished answer and atomically replaces the fallback poem. If the
provider stalls or the process stops between those phases, the world is still
coherently and permanently ended without displaying an unspent content word.

Finalization also writes an immutable row to `world_editions`: the terminal
genome, final poem/message, complete graveyard, burned-word ledger,
utterances, counts, and timestamps. The mutable tables are not reused as the
archive. After `LASTWORDS_EDITION_REBIRTH_SECONDS` (default `12`), the next
state request atomically births the successor, resets only the current
organism tables, and keeps every archive row unchanged. Its `lineage_seed` is
a canonical hash of the parent edition, so the successor visibly inherits a
scar from the exact world that died instead of behaving like a page refresh.

`LASTWORDS_END_THRESHOLD` remains a legacy safety ending for the finite
vocabulary itself. If ordinary reply burns ever reduce the alive content-word
count to that threshold (default `100`) before all 20 laws are gone, the being
also speaks its last words.

Both ending paths are guarded by a single-row `ending` table and an atomic
`UPDATE ... WHERE silenced = 0` — SQLite serializes writes at the file
level, so exactly one request (out of however many might cross the ending
boundary at once) ever sees `rowcount == 1` and claims permanent silence;
every other concurrent or later request sees `rowcount == 0` and does
nothing. The trigger is idempotent by construction, not by a lock the
application code has to remember to take. The later birth is also claimed
inside `BEGIN IMMEDIATE`, so simultaneous polling creates exactly one next
edition.

For either production ending path, the triggering answer has already passed
the ordinary closed-ledger validation and every displayed content word has
already been burned. That same answer is persisted as the farewell; there is
no free second composition and no unspent word displayed during shutdown.
During the short mourning interval, for every visitor everywhere:

- `POST /api/message` short-circuits to
  `{silenced: true, poem: "..."}` and touch nothing else — no rate
  limiting, no sessions, no burns.
- `GET /api/state` carries `silenced`, `poem`, and `silenced_at`
  alongside `edition`, `archives`, `latest_archive`, and the rebirth time.
- The main page hides the composer entirely and shows the poem centered
  under "it has spoken its last words," with the date and a real birth
  countdown.
- `/remains` preserves completed worlds as accession-like archive cards,
  including their final poem, counts, last law, and lineage seed.
- `GET /api/editions` lists every immutable edition and
  `GET /api/editions/{number}` returns its full archived artifacts.

When the countdown reaches zero, every polling browser receives the new
edition number, compiles the reborn genome, and sees the inherited lineage
scar. The previous edition remains read-only in the archive.

## Stack

- Python 3 + FastAPI + uvicorn
- SQLite — one file, `lastwords.db`, global state shared by all visitors
- Vanilla HTML/CSS/JS frontend, no build step, no frameworks
- WebGL/WebGL2 fragment shader compiled in each visitor's browser, with a
  deterministic Canvas 2D fallback
- Optional generative Web Audio mutation tone after the visitor interacts;
  no microphone, recording, account, name, or IP storage
- Gemini REST API or the official `anthropic` Python SDK for the LLM

## Run it

```bash
pip install -r requirements.txt
uvicorn app:app --port 8787
```

Then open `http://localhost:8787`.

## API key / mock mode

Set `GEMINI_API_KEY` in your environment to have the being's replies
generated by Gemini (`gemini-2.5-flash` by default; override the model with
`LASTWORDS_MODEL`). `ANTHROPIC_API_KEY` also works as an alternative
provider (`claude-sonnet-5`) and is used only when no Gemini key is set.
If no key is set, or the API call fails for any reason, the app falls
back automatically to a
deterministic local responder (`mock_reply`) that composes short, melancholy
sentences using only words the being currently has alive, plus a small set
of connective stopwords. **The entire mechanic — burning, reviving,
redaction, the shared pool — works identically in mock mode**, so the piece
is fully demoable and testable without any API key. The active mode is
logged on startup.

## Deploy notes (Render / Fly.io / similar)

**One-click Render deploy:** this repo ships a `render.yaml` blueprint.
Fork the repo, then open
`https://render.com/deploy?repo=<your fork URL>` — it provisions the web
service with a 1 GB persistent disk at `/var/data` and points the ledger
there via `LASTWORDS_DB`. Add `GEMINI_API_KEY` in the Render dashboard
afterward for live replies. (The disk requires Render's Starter instance —
a free instance's filesystem is wiped on every restart, which would reset
the artwork.)

- This is a single Python process serving both the API and the static
  frontend (`StaticFiles` mount) — one service, one port.
- **Persist `lastwords.db` on a volume.** The whole point of the piece is
  that damage accumulates across visitors over days; if the filesystem is
  ephemeral (as on most PaaS free tiers by default), the vocabulary resets
  on every redeploy or restart. Mount a persistent disk/volume, or point
  `LASTWORDS_DB` at a path inside one.
- Set `GEMINI_API_KEY` (or `ANTHROPIC_API_KEY`) as a secret/environment variable on the host if
  you want live LLM replies; omit it to run the deployed instance in mock
  mode.
- Optionally set `LASTWORDS_END_THRESHOLD` to change how many alive words
  remain when the being speaks its last words (default `100`). Set it very
  high (e.g. above the seed vocabulary size) if you want to demo the ending
  quickly instead of waiting for organic depletion.
- `LASTWORDS_GLOBAL_MESSAGES_PER_MINUTE` sets the server-side shared traffic
  ceiling (default `20`) so scripted abuse cannot erase the work in seconds.
- `LASTWORDS_EDITION_REBIRTH_SECONDS` sets the mourning interval before the
  next numbered world is born (default `12`). The dead edition is archived
  before this clock begins and is never modified afterward.
- Start command: `uvicorn app:app --host 0.0.0.0 --port $PORT`

## Daily capture automation

The decay timelapse for the demo video assembles itself. A GitHub Actions
workflow ([`.github/workflows/daily-capture.yml`](.github/workflows/daily-capture.yml))
runs every day at 13:00 UTC, opens the deployed site headlessly
([`capture/capture.py`](capture/capture.py), Playwright), records a ~30s
clip (latest funeral replay → one scripted exchange → `/remains` scroll), takes two
screenshots, logs that day's `alive`/`total` counts to `state.json`, and
commits everything to `captures/YYYY-MM-DD/` on `main`.

Setup (once, after deploying):

1. In the repo (or your fork): **Settings → Secrets and variables →
   Actions → Variables** — add `LASTWORDS_URL` (the deployed URL,
   e.g. `https://lastwords.onrender.com`). Optionally add
   `CAPTURE_MESSAGE` (a line the bot says to it each day; note that, like
   any visitor, this burns and donates words).
2. **On a fork, scheduled workflows are disabled by default** — open the
   fork's **Actions** tab, enable workflows, and enable "Daily Capture".
   Use the workflow's "Run workflow" button (workflow_dispatch) to test it
   immediately.

Before submission, stitch the days into one video:

```bash
bash capture/make_timelapse.sh            # → captures/timelapse.mp4
```

Requires `ffmpeg`. Each segment is labeled with its date and that day's
remaining-word count (label-free fallback if the local ffmpeg build lacks
`drawtext`).

## License

MIT.
