// THE REMAINS — remains.js
// The whole vocabulary as one flowing field. Alive words render as text.
// Burned words render as blackout bars — the actual word text is used only
// to compute a bar width, then discarded; it is never written into the DOM
// (no textContent, no data-* attribute, no title carrying the word itself).

(() => {
  "use strict";

  const POLL_MS = 2500;

  const fieldEl = document.getElementById("word-field");
  const aliveCountEl = document.getElementById("alive-count");
  const totalCountEl = document.getElementById("total-count");
  const poemBlock = document.getElementById("final-poem-block");
  const poemText = document.getElementById("final-poem-text");
  const poemDate = document.getElementById("final-poem-date");
  const editionLabel = document.getElementById("remains-edition-label");
  const archiveCount = document.getElementById("archive-count");
  const archiveLedger = document.getElementById("archive-ledger");

  // word -> status, so we can detect transitions between polls
  let known = new Map();
  let currentAlive = null;

  function animateCountTo(el, from, to) {
    if (from === null || from === to) {
      el.textContent = to.toLocaleString();
      return;
    }
    const duration = 700;
    const start = performance.now();
    const diff = to - from;
    function frame(now) {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      el.textContent = Math.round(from + diff * eased).toLocaleString();
      if (t < 1) requestAnimationFrame(frame);
      else el.textContent = to.toLocaleString();
    }
    requestAnimationFrame(frame);
  }

  function formatDate(iso) {
    if (!iso) return "";
    try {
      const d = new Date(iso);
      return d.toLocaleString(undefined, {
        year: "numeric",
        month: "long",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch (e) {
      return iso;
    }
  }

  function renderPoem(silenced, poem, silencedAt) {
    if (!silenced || !poem) {
      poemBlock.classList.add("hidden");
      return;
    }
    poemBlock.classList.remove("hidden");
    poemText.textContent = poem;
    poemDate.textContent = formatDate(silencedAt);
  }

  function shortLineage(seed) {
    return String(seed || "00000000")
      .replace(/[^a-f0-9]/gi, "")
      .slice(0, 8)
      .padEnd(8, "0")
      .toUpperCase();
  }

  function renderArchive(current, editions) {
    const safeEditions = Array.isArray(editions) ? editions : [];
    if (editionLabel && current) {
      editionLabel.textContent =
        `${current.label || "WORLD 001"} · ${current.status === "silenced" ? "MOURNING" : "LIVING"}`;
    }
    archiveCount.textContent =
      `${safeEditions.length.toLocaleString()} ${safeEditions.length === 1 ? "world" : "worlds"} buried`;
    archiveLedger.replaceChildren();

    if (safeEditions.length === 0) {
      const empty = document.createElement("p");
      empty.className = "archive-empty";
      empty.textContent =
        "The first world is still deciding how it will die.";
      archiveLedger.appendChild(empty);
      return;
    }

    const fragment = document.createDocumentFragment();
    safeEditions.forEach((edition) => {
      const card = document.createElement("article");
      card.className = "edition-card";

      const heading = document.createElement("div");
      heading.className = "edition-card-heading";
      const title = document.createElement("h3");
      title.className = "edition-card-title";
      title.textContent = edition.label || `WORLD ${edition.number}`;
      const status = document.createElement("span");
      status.className = "edition-card-status";
      status.textContent = "ARCHIVED / READ ONLY";
      heading.append(title, status);

      const poem = document.createElement("p");
      poem.className = "edition-card-poem";
      poem.textContent = edition.final_poem || "I am.";

      const meta = document.createElement("p");
      meta.className = "edition-card-meta";
      const lawCount = Number(edition.world_version || 0);
      const messages = Number(edition.message_count || 0);
      const alive = Number(edition.alive_count || 0);
      meta.textContent =
        `${lawCount} laws removed · ${messages} questions · ${alive} words survived · closed ${formatDate(edition.died_at)}`;

      const lineage = document.createElement("p");
      lineage.className = "edition-card-lineage";
      lineage.textContent =
        `LINEAGE ${shortLineage(edition.lineage_seed)} · LAST LOSS ${String(edition.last_law || "unknown").toUpperCase()}`;

      card.append(heading, poem, meta, lineage);
      fragment.appendChild(card);
    });
    archiveLedger.appendChild(fragment);
  }

  function makeWordNode(word, status, justChanged) {
    if (status === "alive") {
      const span = document.createElement("span");
      span.className = "rw alive";
      span.textContent = word;
      return span;
    }
    // burned: compute width from length, then drop the text entirely.
    const len = word.length;
    const bar = document.createElement("span");
    bar.className = "rw bar";
    if (justChanged) bar.classList.add("bar-fading");
    bar.style.width = Math.max(0.6, len * 0.62) + "em";
    bar.title = "erased";
    // no textContent, no data attribute — the word itself is gone.
    return bar;
  }

  function fullRender(words) {
    fieldEl.innerHTML = "";
    known = new Map();
    const frag = document.createDocumentFragment();
    words.forEach((entry, i) => {
      known.set(entry.w, entry.s);
      frag.appendChild(makeWordNode(entry.w, entry.s, false));
      if (i < words.length - 1) frag.appendChild(document.createTextNode(" "));
    });
    fieldEl.appendChild(frag);
  }

  function diffRender(words) {
    // Only rebuild if the word SET or any status changed — cheap check.
    let changed = words.length !== known.size;
    const changedWords = new Set();
    if (!changed) {
      for (const entry of words) {
        const prev = known.get(entry.w);
        if (prev === undefined) {
          changed = true;
          break;
        }
        if (prev !== entry.s) {
          changedWords.add(entry.w);
        }
      }
    }
    if (changedWords.size === 0 && !changed) {
      return; // nothing to do
    }
    if (changed) {
      // set membership changed (rare) — full rebuild, no special fade
      fullRender(words);
      return;
    }

    fieldEl.innerHTML = "";
    known = new Map();
    const frag = document.createDocumentFragment();
    words.forEach((entry, i) => {
      known.set(entry.w, entry.s);
      frag.appendChild(makeWordNode(entry.w, entry.s, changedWords.has(entry.w)));
      if (i < words.length - 1) frag.appendChild(document.createTextNode(" "));
    });
    fieldEl.appendChild(frag);

    // settle the fade class after the transition plays
    setTimeout(() => {
      fieldEl.querySelectorAll(".bar-fading").forEach((el) => {
        el.classList.remove("bar-fading");
      });
    }, 2200);
  }

  async function poll() {
    try {
      const [wordsRes, stateRes, editionsRes] = await Promise.all([
        fetch("/api/words"),
        fetch("/api/state"),
        fetch("/api/editions"),
      ]);
      const words = await wordsRes.json();
      const state = await stateRes.json();
      const editionData = await editionsRes.json();

      animateCountTo(aliveCountEl, currentAlive, state.alive);
      totalCountEl.textContent = state.total.toLocaleString();
      currentAlive = state.alive;

      renderPoem(state.silenced, state.poem, state.silenced_at);
      renderArchive(editionData.current, editionData.editions);

      if (known.size === 0) {
        fullRender(words);
      } else {
        diffRender(words);
      }
    } catch (e) {
      // silent — next poll retries
    }
  }

  poll();
  setInterval(poll, POLL_MS);
})();
