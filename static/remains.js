// THE REMAINS — remains.js
// The whole vocabulary as one flowing field. Alive words render as text.
// Burned words render as blackout bars — the actual word text is used only
// to compute a bar width, then discarded; it is never written into the DOM
// (no textContent, no data-* attribute, no title carrying the word itself).

(() => {
  "use strict";

  const POLL_MS = 10000;

  const fieldEl = document.getElementById("word-field");
  const aliveCountEl = document.getElementById("alive-count");
  const totalCountEl = document.getElementById("total-count");
  const poemBlock = document.getElementById("final-poem-block");
  const poemText = document.getElementById("final-poem-text");
  const poemDate = document.getElementById("final-poem-date");

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
      const [wordsRes, stateRes] = await Promise.all([
        fetch("/api/words"),
        fetch("/api/state"),
      ]);
      const words = await wordsRes.json();
      const state = await stateRes.json();

      animateCountTo(aliveCountEl, currentAlive, state.alive);
      totalCountEl.textContent = state.total.toLocaleString();
      currentAlive = state.alive;

      renderPoem(state.silenced, state.poem, state.silenced_at);

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
