// LAST WORDS — app.js
// Vanilla JS. No frameworks, no build step, fully offline-capable.

(() => {
  "use strict";

  const STATE_POLL_MS = 8000;
  const TYPE_MS_PER_WORD = 40;
  const INTRO_KEY = "lastwords_intro_seen";
  const SESSION_KEY = "lastwords_session_id";

  const conversationEl = document.getElementById("conversation");
  const graveyardFeedEl = document.getElementById("graveyard-feed");
  const aliveCountEl = document.getElementById("alive-count");
  const totalCountEl = document.getElementById("total-count");
  const form = document.getElementById("message-form");
  const input = document.getElementById("message-input");
  const sendButton = document.getElementById("send-button");
  const introOverlay = document.getElementById("intro-overlay");
  const introDismiss = document.getElementById("intro-dismiss");
  const composerEl = document.getElementById("composer");
  const silenceBlock = document.getElementById("silence-block");
  const silencePoemTextEl = document.getElementById("silence-poem-text");
  const silencePoemDateEl = document.getElementById("silence-poem-date");

  let currentAlive = null;
  let greeted = false;
  let sending = false;
  let isSilenced = false;

  // ---------------------------------------------------------------- session

  function getSessionId() {
    let id = localStorage.getItem(SESSION_KEY);
    if (!id) {
      id = crypto.randomUUID();
      localStorage.setItem(SESSION_KEY, id);
    }
    return id;
  }

  const sessionId = getSessionId();

  // ------------------------------------------------------------------ intro

  function maybeShowIntro() {
    if (!localStorage.getItem(INTRO_KEY)) {
      introOverlay.classList.remove("hidden");
    }
  }

  introDismiss.addEventListener("click", () => {
    localStorage.setItem(INTRO_KEY, "1");
    introOverlay.classList.add("hidden");
    input.focus();
  });

  // -------------------------------------------------------------- counters

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
      const val = Math.round(from + diff * eased);
      el.textContent = val.toLocaleString();
      if (t < 1) {
        requestAnimationFrame(frame);
      } else {
        el.textContent = to.toLocaleString();
      }
    }
    requestAnimationFrame(frame);
  }

  function updateCounters(alive, total) {
    animateCountTo(aliveCountEl, currentAlive, alive);
    totalCountEl.textContent = total.toLocaleString();
    if (currentAlive !== null && alive < currentAlive) {
      aliveCountEl.classList.add("pulse");
      setTimeout(() => aliveCountEl.classList.remove("pulse"), 1200);
    }
    currentAlive = alive;
  }

  // -------------------------------------------------------------- messages

  function scrollToBottom() {
    conversationEl.scrollTop = conversationEl.scrollHeight;
  }

  function addUserMessage(text) {
    const wrap = document.createElement("div");
    wrap.className = "msg user";
    const line = document.createElement("div");
    line.className = "msg-line";
    line.textContent = text;
    wrap.appendChild(line);
    conversationEl.appendChild(wrap);
    scrollToBottom();
    return wrap;
  }

  function addReviveLine(container, revivedWords) {
    if (!revivedWords || revivedWords.length === 0) return;
    const line = document.createElement("div");
    line.className = "revive-line";
    const spans = revivedWords
      .map((w) => `<span class="rw">${escapeHtml(w)}</span>`)
      .join(", ");
    line.innerHTML = `you gave back: ${spans}`;
    container.appendChild(line);
  }

  function escapeHtml(s) {
    const div = document.createElement("div");
    div.textContent = s;
    return div.innerHTML;
  }

  // Render an AI message word-by-word (typewriter), redacting ghost
  // segments as blocks. `segments` is [{t:'w', s:'hello'}|{t:'x'}].
  // `burnedNow` is the list of words that got burned by this exact reply,
  // used to decide which rendered words should glow ember and settle.
  function addAiMessageAnimated(segments, burnedNow) {
    const wrap = document.createElement("div");
    wrap.className = "msg ai";
    const line = document.createElement("div");
    line.className = "msg-line";
    wrap.appendChild(line);
    conversationEl.appendChild(wrap);
    scrollToBottom();

    const burnedSet = new Set((burnedNow || []).map((w) => w.toLowerCase()));
    const cursor = document.createElement("span");
    cursor.className = "typing-cursor";
    cursor.textContent = "▍";
    line.appendChild(cursor);

    let i = 0;

    function coreWordOf(str) {
      const m = str.toLowerCase().match(/[a-z']+/);
      if (!m) return null;
      let w = m[0];
      if (w.endsWith("'s")) w = w.slice(0, -2);
      w = w.replace(/^'+|'+$/g, "");
      return w || null;
    }

    function renderNext() {
      if (i >= segments.length) {
        cursor.remove();
        scrollToBottom();
        return;
      }
      const seg = segments[i];
      i += 1;

      const isFirst = line.childNodes.length <= 1; // only cursor present
      if (!isFirst) {
        line.insertBefore(document.createTextNode(" "), cursor);
      }

      if (seg.t === "x") {
        const span = document.createElement("span");
        span.className = "redacted";
        span.title = "a word it no longer has";
        span.textContent = "▓▓▓";
        line.insertBefore(span, cursor);
      } else {
        const span = document.createElement("span");
        span.className = "word";
        span.textContent = seg.s;
        const core = coreWordOf(seg.s);
        if (core && burnedSet.has(core)) {
          span.classList.add("burning");
          // settle back to normal text color after the glow
          setTimeout(() => span.classList.remove("burning"), 2400);
        }
        line.insertBefore(span, cursor);
      }

      scrollToBottom();
      setTimeout(renderNext, TYPE_MS_PER_WORD);
    }

    renderNext();
    return wrap;
  }

  function addSystemLine(text) {
    const el = document.createElement("div");
    el.className = "system-line";
    el.textContent = text;
    conversationEl.appendChild(el);
    scrollToBottom();
  }

  // ------------------------------------------------------------- the ending

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

  function applySilencedUI(poem, silencedAt) {
    isSilenced = true;
    composerEl.classList.add("silenced");
    silenceBlock.classList.remove("hidden");
    if (poem) silencePoemTextEl.textContent = poem;
    if (silencedAt) silencePoemDateEl.textContent = formatDate(silencedAt);
  }

  // -------------------------------------------------------------- graveyard

  function renderGraveyard(entries) {
    graveyardFeedEl.innerHTML = "";
    entries.forEach((e) => {
      const row = document.createElement("div");
      row.className = "grave-entry";

      const wordSpan = document.createElement("span");
      if (e.kind === "burn") {
        wordSpan.className = "grave-word burned";
        wordSpan.textContent = e.word;
      } else if (e.kind === "ghost") {
        wordSpan.className = "grave-word ghost";
        wordSpan.textContent = "▓▓▓";
        wordSpan.title = e.word;
      } else if (e.kind === "revive") {
        wordSpan.className = "grave-word revived";
        wordSpan.textContent = e.word;
      } else {
        wordSpan.className = "grave-word";
        wordSpan.textContent = e.word;
      }

      const tsSpan = document.createElement("span");
      tsSpan.className = "grave-ts";
      tsSpan.textContent = e.relative || "";

      row.appendChild(wordSpan);
      row.appendChild(tsSpan);
      graveyardFeedEl.appendChild(row);
    });
  }

  // ------------------------------------------------------------------ API

  async function fetchState() {
    try {
      const res = await fetch("/api/state");
      if (!res.ok) return;
      const data = await res.json();
      updateCounters(data.alive, data.total);
      renderGraveyard(data.graveyard || []);
      if (data.silenced) {
        applySilencedUI(data.poem, data.silenced_at);
      }
    } catch (e) {
      // silent — network hiccup, next poll will retry
    }
  }

  async function sendGreeting() {
    try {
      const res = await fetch("/api/greet", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId }),
      });
      const data = await res.json();
      handleReplyPayload(data);
    } catch (e) {
      addSystemLine("(it did not answer)");
    }
  }

  function handleReplyPayload(data) {
    if (data.alive !== undefined) updateCounters(data.alive, data.total);

    if (data.silenced) {
      // Either this call just triggered the ending, or the being was
      // already silent — either way, no more animated replies, just the poem.
      applySilencedUI(data.poem, data.silenced_at);
      fetchState();
      return;
    }

    addAiMessageAnimated(data.segments || [], data.burned_now || []);
    if (!data.rate_limited) {
      fetchState();
    }
  }

  async function sendMessage(text) {
    if (sending) return;
    sending = true;
    sendButton.disabled = true;

    const userWrap = addUserMessage(text);

    try {
      const res = await fetch("/api/message", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, session_id: sessionId }),
      });
      const data = await res.json();
      addReviveLine(userWrap, data.revived);
      handleReplyPayload(data);
    } catch (e) {
      addSystemLine("(the words did not reach it)");
    } finally {
      sending = false;
      sendButton.disabled = false;
    }
  }

  // ------------------------------------------------------------------ init

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    if (isSilenced) return;
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    sendMessage(text);
  });

  maybeShowIntro();

  (async () => {
    await fetchState();
    setInterval(fetchState, STATE_POLL_MS);

    if (!greeted) {
      greeted = true;
      if (!isSilenced) {
        sendGreeting();
      }
    }
  })();
})();
