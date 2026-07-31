# Third-Party Attributions

This file separates project-authored work from external libraries, services,
and tooling used by LAST WORDS. It is also a pre-submission provenance check.
Resolve every item marked **CONFIRM** before publishing the Devpost entry.

## Project-authored work

Subject to the authorship confirmation below, the following files and creative
systems are original work made for LAST WORDS:

- The concept, interaction design, interface copy, and visual direction
- The twenty-law world genome and word-to-law sacrifice system
- The GLSL/WebGL organism renderer and deterministic Canvas 2D fallback in
  `static/world.js`
- The backend ledger, constraint validation, concurrency logic, edition
  archive, and API in `app.py`
- The finite vocabulary curated in `seed_words.py`
- The HTML, CSS, and client-side interaction code in `static/`
- The deterministic local responder and project tests
- The generated Web Audio mutation tone; there is no bundled music or sound
  recording

**Student creator:** Eden — concept direction, creative coding, systems
integration, interaction decisions, and final testing.

`static/world.js` and its shader were developed for this project and were not
adapted from a specific online shader or tutorial. They use commonplace
procedural hash/noise, signed-distance-field, and particle techniques rather
than copied visual source. If the student later identifies an adapted source,
that source must be added here before submission.

## Runtime libraries and services

| Dependency | How it is used | Source / terms |
| --- | --- | --- |
| [FastAPI](https://github.com/fastapi/fastapi) | HTTP API, request validation, and static-file service | MIT License; copyright Sebastián Ramírez and FastAPI contributors |
| [Uvicorn](https://github.com/Kludex/uvicorn) | ASGI production server | BSD 3-Clause License; copyright Encode OSS Ltd and contributors |
| [Pydantic](https://github.com/pydantic/pydantic) | Request-model validation through FastAPI | MIT License; copyright Pydantic Services Inc. and contributors |
| [SQLite](https://www.sqlite.org/copyright.html) | Shared vocabulary, world genome, transactions, events, and edition archive | SQLite source is dedicated to the public domain |
| [Google Gemini API](https://ai.google.dev/gemini-api/docs) | Primary optional language-model provider, called by REST when `GEMINI_API_KEY` is configured | External service; use is governed by Google's applicable API terms |
| [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python) | Optional alternative language-model client when Gemini is not configured | MIT License; copyright Anthropic, PBC |

The deployed build also has a deterministic local response mode. If no model
key is configured or a provider call fails, the local responder is used.
Before submission, report the deployed mode accurately in the project
description and demo captions.

## Browser platform APIs

The artwork uses native browser capabilities, not third-party rendering or
audio assets:

- WebGL / WebGL2 and GLSL for the live compiled organism
- Canvas 2D as a deterministic visual fallback
- Web Audio API for a generated mutation tone after user interaction
- `fetch`, `localStorage`, `requestAnimationFrame`, and `ResizeObserver`

The CSS specifies a system-font fallback stack. No webfont file or remote font
request is bundled. `IBM Plex Mono` is only a preferred local family name and
is not distributed by this repository.

## Capture and automation tooling

| Dependency | How it is used | Source / terms |
| --- | --- | --- |
| [Playwright for Python](https://github.com/microsoft/playwright-python) | Records actual browser sessions and captures screenshots for the demo | Apache License 2.0; copyright Microsoft Corporation |
| [FFmpeg](https://ffmpeg.org/) | Encodes captured clips into the submission video | FFmpeg is distributed under LGPL/GPL terms depending on the build; it is a build tool, not bundled in this repository |
| [GitHub Actions](https://docs.github.com/actions) | Runs the scheduled capture workflow | Hosted automation service |
| [`actions/checkout`](https://github.com/actions/checkout) | Checks out the repository in the capture workflow | MIT License |
| [`actions/setup-python`](https://github.com/actions/setup-python) | Installs Python in the capture workflow | MIT License |
| [`actions/upload-artifact`](https://github.com/actions/upload-artifact) | Uploads recorded capture artifacts | MIT License |
| [Render](https://render.com/) | Application host for the public FastAPI service and persistent SQLite disk | External hosting service |

## Visual and audio assets

### `static/lastwords-grain.png` — custom generated asset

The repository contains a 1600×1200 paper-grain texture at
`static/lastwords-grain.png`. It was generated specifically for this redesign
without a stock image or other source image. The file is currently untracked
in the local git history, and the exact generator/model was not recorded.

**CONFIRM — generator metadata:** identify the exact tool or model if the
creation record can be recovered. Use this truthful form:

- `Custom AI-generated paper-grain texture created specifically for LAST WORDS
  using [MODEL/TOOL], [DATE]; no stock or source image was used.`

If the exact model cannot be recovered before submission, retain the confirmed
facts without guessing:

> Custom AI-generated paper-grain texture created specifically for LAST WORDS;
> no stock or source image was used. Exact generator metadata was not retained.

### Other assets

No stock photography, icon pack, prerecorded music, sound effect, remote
image, or bundled font was found in the current project files.

## AI-use disclosure

OpenAI Codex assisted with implementation, debugging, design iteration,
capture tooling, testing, and submission-copy drafting. Eden directed the
concept choices, selected and revised the experience, integrated the system,
and is responsible for the final submission. The public runtime provider is
reported by `/api/state` as `response_mode`; record its deployed value here
after the final production smoke test.

## Final attribution check

- [ ] Student creator names and roles added.
- [ ] Shader/code originality confirmed or adapted sources listed.
- [ ] `lastwords-grain.png` generator metadata added if recoverable; otherwise
      use the conservative disclosure above.
- [ ] Final deployment host confirmed.
- [ ] Active runtime response mode confirmed.
- [ ] AI-assisted creation process disclosed according to competition and
      school requirements.
- [ ] Every new asset added after this review is credited here.
