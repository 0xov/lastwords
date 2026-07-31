# LAST WORDS — A Self-Erasing World

> Submission copy draft. Replace every bracketed placeholder and complete the
> verification checklist before pasting this into Devpost.

## Submission links

- Live project: [LAST WORDS](https://lastwords-793366432413.asia-northeast3.run.app/)
- Public source: [github.com/0xov/lastwords](https://github.com/0xov/lastwords)
- 60-second demo: [direct MP4](https://raw.githubusercontent.com/0xov/lastwords/main/submission/LAST_WORDS_60S_DEMO.mp4)
- Hackathon: [Hack the Arts](https://hackthearts.devpost.com/)
- Safe internal submission deadline: **August 1, 2026 at 11:45 PM EDT**
  (the time shown on the Hack the Arts overview page)

## One-line hook

To ask the artwork a question, you must permanently delete one executable law
from the world everyone is watching.

## Short description

LAST WORDS is a shared digital organism with twenty laws and a finite
vocabulary. Each visitor previews a loss, sacrifices a word, and removes the
law it carries from the live shader. The browser recompiles the damaged world,
the being answers under its new limits, and every other visitor inherits the
same absence.

## Inspiration

Most interactive art lets the audience choose an output while the system that
creates it remains safe. We wanted the interaction to have a real cost.

LAST WORDS asks a different question: what if speaking to an artwork changed
the conditions under which it could ever appear again? A visitor does not
select a color, scene, or animation. They decide which capability the work
must lose before it is allowed to answer.

## What it does

The piece begins as one shared world with twenty executable laws, including
gravity, memory, attraction, turbulence, light, symmetry, touch, sound, depth,
continuity, and agency.

Before sending a question, a visitor must choose one living word. Each offered
word carries one law. Hovering or focusing the word previews the missing
physics without committing it. Submitting the question burns the word and
sets its law to zero in the shared genome.

That change is not a prerecorded visual transition. The browser inserts the
new genome into the GLSL fragment shader, compiles it, and shows the changed
source, build number, and compile receipt on screen. Other open browsers poll
the same state and compile the same damaged world.

The being then replies with the vocabulary it still has. Every content word in
its displayed reply is spent from the shared language pool. A visitor can
donate a lost language word back by typing it, but the executable law attached
to a sacrifice never returns within that world.

After the twentieth law disappears, the being speaks its final words. Its
final genome, losses, and farewell remain preserved as an immutable edition.
A new numbered world can be born afterward, but WORLD 001 is not reset or
overwritten. The archive turns collective interaction into a lineage of
different worlds rather than an endlessly refreshing effect.

## How we built it

The backend is a Python/FastAPI service with a SQLite ledger. A short
`BEGIN IMMEDIATE` transaction validates and claims each sacrifice, burns the
selected word, changes exactly one remaining law, and increments the shared
world version. This prevents two simultaneous visitors from deleting the same
law.

The language-model call runs outside the write lock. The server gives the
model the surviving vocabulary and missing laws, validates the result against
the closed word ledger, retries once when needed, and visibly redacts any
remaining violation. If no model API is configured or the provider fails, a
deterministic local responder keeps the complete artwork mechanic functional.

The frontend is framework-free HTML, CSS, and JavaScript. Its custom WebGL
engine bakes all twenty genome values into real fragment-shader source and
compiles a new program after every committed mutation. Uniforms provide a
reversible hover preview without creating a false build. A deterministic
Canvas 2D renderer preserves the experience on devices without WebGL.

The `/remains` page renders the shared vocabulary as erasure poetry. Living
words remain readable. Burned words become blackout bars, and the page updates
when another visitor changes the ledger.

## Why the technology is the medium

Remove any major technical layer and the artwork stops being this artwork:

- Without a shared database, a sacrifice would be a private animation instead
  of a consequence inherited by strangers.
- Without concurrency control, two visitors could claim incompatible versions
  of the same world.
- Without live shader compilation, the audience would see a representation of
  loss rather than changing the executable rules that create the image.
- Without constrained generation and server-side validation, the being would
  not have to improvise inside a vocabulary it has actually spent.
- Without network synchronization, there would be no single collective
  organism or edition history.

The code is not a tool used to imitate an existing art form. The shared,
irreversible, computational process is the work.

## Challenges

### Making loss real without making the demo fragile

The central difficulty was keeping irreversible audience actions safe under
concurrency. We separated each interaction into two short transactions around
the slower model call. Sacrifices use version checks and atomic updates, while
the ending has one claim path so only one request can complete the final
world.

### Giving an AI a truly finite language

A prompt alone cannot enforce a vocabulary. We built a closed server-side
ledger, token validation, one retry, and a final visible redaction path. The
model can attempt an unavailable word, but the artwork will not silently let
it cheat.

### Making twenty parameters feel like twenty different absences

Each law affects the generated form, motion, persistence, interaction, sound,
or color in a distinct way. The same genome also drives the Canvas fallback,
so the conceptual rules survive across rendering capabilities.

### Showing proof without turning the work into a dashboard

The interface keeps the organism central, but exposes the current build,
changed shader constant, compile status, law consequence, and shared remains
as evidence that the mutation actually happened.

## Accomplishments

- The audience changes executable image-making rules, not a prepared choice
  tree.
- Preview is reversible; sacrifice is committed and shared.
- Every browser receives the same versioned genome and recompiles it locally.
- The language model is constrained by a finite, server-enforced vocabulary.
- The piece stays functional with a deterministic offline response path.
- A completed world remains inspectable as an edition instead of being erased
  by the birth of the next one.
- The interface works on desktop and mobile, with WebGL and Canvas rendering
  paths.

## What we learned

Interactivity becomes more meaningful when the audience changes a system's
future possibilities, not just its current appearance. We also learned that
an AI constraint only becomes part of the artwork when the software enforces
it independently of the prompt.

The project changed our idea of generative art: the important output is not a
single image. It is the irreversible history of rules removed by different
people and the family of worlds that history produces.

## What's next

- Let visitors compare archived editions by final genome and vocabulary.
- Turn each edition's sequence of shader mutations into a replayable score.
- Add an installation mode that projects the world while phones become the
  sacrifice interface.
- Export an edition as a self-contained archival bundle without making it
  editable.

## Technologies used

- Python 3
- FastAPI
- Uvicorn
- SQLite
- Vanilla HTML, CSS, and JavaScript
- WebGL/WebGL2 and GLSL
- Canvas 2D fallback
- Web Audio API
- Google Gemini API via REST, when configured
- Anthropic Python SDK as an optional alternative provider
- Playwright and FFmpeg for actual-screen capture tooling
- GitHub Actions for scheduled capture
- Render for hosting

## How to experience it

1. Open [the live project](https://lastwords-793366432413.asia-northeast3.run.app/) in two browser windows.
2. In the first window, hover or focus each offered word and watch the world
   preview that law's absence.
3. Choose one word, ask a question, and submit.
4. Watch the impact, changed law, build number, shader source, and compile
   receipt.
5. Leave the second window untouched. Within the state-sync interval, it
   should inherit the same build and missing physics.
6. Open `/remains` to see the shared language ledger.
7. Open [the immutable world archive](https://lastwords-793366432413.asia-northeast3.run.app/remains#world-archive) to inspect completed numbered worlds.

## Judging fit

| Criterion | Judge-visible evidence |
| --- | --- |
| Creativity & Originality — 30% | The audience permanently removes the executable rules that generate the art; each completed loss history becomes an edition. |
| Use of Technology — 25% | Atomic shared state, constrained generation, closed-ledger validation, live GLSL source generation and compilation, WebGL/Canvas rendering, and synchronization all carry conceptual meaning. |
| Interactivity & Experience — 20% | A visitor previews a consequence, makes an irreversible choice, receives a law-aware reply, and watches another browser inherit it. |
| Execution — 15% | Working live demo, visible compile proof, concurrency checks, provider fallback, responsive interface, archive, tests, and public source. |
| Theme Alignment — 10% | The work is the shared computational process; it cannot be reproduced as a static image or traditional artwork. |

## Third-party disclosure

See [`ATTRIBUTIONS.md`](../ATTRIBUTIONS.md) for libraries, APIs, capture tools,
and the generator-metadata check for the custom paper-grain texture. Do not
submit until every item marked `CONFIRM` in that file is resolved.

## Final verification before pasting

- [ ] Replace all bracketed URL and hosting placeholders.
- [ ] Confirm the deployed provider mode; do not call a fallback response AI.
- [ ] Verify WORLD 001 remains archived after WORLD 002 is born.
- [ ] Open the live URL in a signed-out/private browser.
- [ ] Open the public repository while signed out.
- [ ] Play the uploaded video with sound off and confirm captions are readable.
- [ ] Confirm every screen shown in the video is the working product.
- [ ] Resolve every `CONFIRM` item in `ATTRIBUTIONS.md`.
- [ ] Submit by the earlier displayed time: August 1, 2026 at 11:45 PM EDT.
