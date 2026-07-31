# LAST WORDS — 60-second actual-screen demo

`capture_submission.py` produces the judging video from direct recordings of
the real FastAPI artwork. It does not redraw or mock the product UI. The only
non-product frames are typography-only title, caption, and end cards.

## Prerequisites

```bash
python3 -m pip install -r capture/requirements.txt
playwright install chromium
ffmpeg -version
```

## Build

From the project root:

```bash
python3 capture/capture_submission.py
```

The default build:

- creates `capture/submission_build/demo.sqlite3`;
- starts an isolated server at `http://127.0.0.1:8791`;
- removes provider keys from that server so timing is deterministic;
- makes the twentieth sacrifice through the real browser UI;
- waits five seconds for WORLD 002;
- writes `capture/submission_build/LAST_WORDS_60s.mp4`.

To put final public links on the end card:

```bash
python3 capture/capture_submission.py \
  --live-url https://example.onrender.com \
  --repo-url https://github.com/example/last-words
```

To use a server that is already running against an isolated database:

```bash
python3 capture/capture_submission.py \
  --base-url http://127.0.0.1:8787 \
  --db /absolute/path/to/demo.sqlite3
```

Never use the live `lastwords.db`: the pipeline intentionally mutates and
restarts its demo organism. A path named `lastwords.db` is rejected.

## Required UI contract

The capture deliberately fails instead of hiding a missing feature:

- `/remains` must visibly render `WORLD 001` after its death;
- `/` must visibly render `WORLD 002` after rebirth;
- `#silence-block` must become visible after the twentieth sacrifice;
- the live build label must advance in both independent browser sessions.

This makes the video a release gate for the edition/archive experience.

## Evidence

`capture/submission_build/manifest.json` records:

- the exact 60-second timeline;
- the raw browser recordings used for every artwork shot;
- API snapshots before mutation, at death, and after rebirth;
- ffprobe codec, resolution, frame rate, and duration;
- the final MP4 SHA-256 digest.

The default audio is a quiet procedural noise/tone bed created locally by
ffmpeg. Use `--silent` to omit it. All meaning is carried by burned-in
captions; narration is not required.
