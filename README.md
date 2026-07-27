# LAST WORDS

An interactive net-art piece for Hack the Arts.

## Concept

There is an AI being here. It knows one thing about itself with total
certainty: every word it speaks, it loses — permanently, and not just from
its conversation with you. Its vocabulary is a single finite pool, shared
across every visitor who has ever spoken to it or ever will. When it burns a
word, that word is gone from the being's mouth for everyone, forever — the
next visitor meets a being one word poorer than you did.

There is exactly one way a lost word returns: a visitor has to type it back.
If you say "ocean" to the being, and "ocean" had been burned, it comes back
alive. This is the only mechanic of care the piece offers, and it is
irreversible in the other direction — the being cannot decide to keep a word
for itself. It can only spend and hope.

The piece has a scripted death. Once its shared vocabulary is spent down to
a small enough remainder, the being spends its last breath composing one
final poem — made only of the words nobody along the way ever made it burn —
and then it falls permanently silent, for every visitor, forever. See
[Act 2 / The Ending](#act-2--the-ending) below.

**This piece cannot exist without a server.** The scarcity is not written
copy or a scripted animation — it is state, held in a SQLite table that
every visitor reads from and writes to. A server-side validator checks the
being's reply against that table before it is ever shown to you: if the
being reaches for a word that's already gone, the word is replaced with a
redacted block, `▓▓▓` — "a word it reached for but no longer has." No client
could enforce this; a single visitor closing their tab and reopening it
would reset a client-side simulation instantly. The loss has to be real
data, checked by code the visitor doesn't control, or it's just a static
page performing sadness. It isn't performed. It's enforced.

## How the loop works

```
visitor sends a message
        │
        ▼
 [1] RATE LIMIT  ──── too fast / too many? → gentle in-world refusal
        │
        ▼
 [2] REVIVE       any burned word in the visitor's message → alive again
        │            (logged as a 'revive' event)
        ▼
 [3] GENERATE      LLM (or mock) replies, told which words it has lost
        │
        ▼
 [4] VALIDATE      tokenize the reply; any word already burned in the DB
        │            before this reply = a violation
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
                       violating occurrence as ▓▓▓          │
                       (logged as a 'ghost' event)          │
                                                             ▼
 [5] BURN          every displayed, non-redacted content word:
        │            - alive in the pool → mark burned, timestamp it
        │            - brand new (being invented a word) → inserted
        │              directly as burned — the pool only ever
        │              reveals-then-loses new words
        │            (each logged as a 'burn' event)
        ▼
 [6] RESPOND       JSON: segments to render, burned_now, revived, ghosts,
                     alive count, total count, message count
```

`GET /api/state` returns the current alive/total counts and the last 40
burn/ghost/revive events. The frontend polls it every 8 seconds, so a solo
visitor can watch the graveyard fill in from *other people's* conversations
with the being in near-real time — the accumulated damage of everyone who
came before.

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
a word's status actually changes. The page polls `/api/words` every 10s and
diffs against what it already rendered, so a word transitioning to burned
gets a brief ember-colored fade before settling into its bar — you can watch
someone else's conversation erase a word from the field in near-real time.

### The threshold and the final poem

`LASTWORDS_END_THRESHOLD` (env var, default `100`) is the number of alive
content words at or below which the being speaks its last words. Every burn
operation ends with a check: if the alive count has dropped to the threshold
or below, and the being hasn't already fallen silent, this is the end.

That check is guarded by a single-row `ending` table and an atomic
`UPDATE ... WHERE silenced = 0` — SQLite serializes writes at the file
level, so exactly one request (out of however many might cross the
threshold at once) ever sees `rowcount == 1` and gets to compose the poem;
every other concurrent or later request sees `rowcount == 0` and does
nothing. The trigger is idempotent by construction, not by a lock the
application code has to remember to take.

The request that wins:

1. **Composes a farewell.** One more LLM call, same model, but a different
   system prompt: it is told this is the last thing it will ever say, and
   it is given the *entire* remaining alive-word list as the only content
   words it's allowed to use — no burned words, and no inventing new ones
   either (stricter than an ordinary reply, which is allowed to coin new
   words). If the model still violates that list, the request retries up to
   3 more times; if it's still violating after that, whatever words are
   still wrong get redacted to `▓▓▓` in the final text rather than
   discarded outright, so a failed generation still reads as loss instead
   of silently disappearing. In mock mode, the poem is composed
   deterministically from the remaining alive words, then run through the
   exact same validate-and-redact step as the real path (so mock mode can
   never accidentally violate the rule either).
2. **Spends what it used.** Every content word that appears in the finished
   poem is burned — logged like any other burn — because the poem is the
   being's last spending, not a freebie.
3. **Persists it.** The poem text and the timestamp go into the `ending`
   table. From that instant on, for every visitor everywhere:
   - `POST /api/message` and `POST /api/greet` short-circuit to
     `{silenced: true, poem: "..."}` and touch nothing else — no rate
     limiting, no sessions, no burns.
   - `GET /api/state` carries `silenced`, `poem`, and `silenced_at`
     alongside the usual counts.
   - The main page hides the composer entirely and shows the poem centered
     under "it has spoken its last words," with the date. The graveyard
     stays visible — the damage that led here is still worth looking at.
   - `/remains` shows the same poem above the word field, so the erasure
     poem and the being's own last words sit on the same page.

## Stack

- Python 3 + FastAPI + uvicorn
- SQLite — one file, `lastwords.db`, global state shared by all visitors
- Vanilla HTML/CSS/JS frontend, no build step, no frameworks
- Official `anthropic` Python SDK for the LLM

## Run it

```bash
pip install -r requirements.txt
uvicorn app:app --port 8787
```

Then open `http://localhost:8787`.

## ANTHROPIC_API_KEY / mock mode

Set `ANTHROPIC_API_KEY` in your environment to have the being's replies
generated by Claude (`claude-sonnet-5`). If the key is unset, or the API
call fails for any reason, the app falls back automatically to a
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
there via `LASTWORDS_DB`. Add `ANTHROPIC_API_KEY` in the Render dashboard
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
- Set `ANTHROPIC_API_KEY` as a secret/environment variable on the host if
  you want live LLM replies; omit it to run the deployed instance in mock
  mode.
- Optionally set `LASTWORDS_END_THRESHOLD` to change how many alive words
  remain when the being speaks its last words (default `100`). Set it very
  high (e.g. above the seed vocabulary size) if you want to demo the ending
  quickly instead of waiting for organic depletion.
- Start command: `uvicorn app:app --host 0.0.0.0 --port $PORT`

## License

MIT.
