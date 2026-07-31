// LAST WORDS — app.js
// Vanilla JS. No frameworks, no build step, fully offline-capable.

(() => {
  "use strict";

  const STATE_POLL_MS = 2500;
  const TYPE_MS_PER_WORD = 92;
  const FUNERAL_STAGGER_MS = 150;
  const MAX_VISIBLE_GRAVES = 10;
  const MAX_VISIBLE_FUNERALS = 10;
  const SESSION_KEY = "lastwords_session_id";
  const DEFAULT_SEND_LABEL = "sacrifice & ask";

  const conversationEl = document.getElementById("conversation");
  let waitingLineEl = document.getElementById("waiting-line");
  const stageLabelEl = document.getElementById("last-utterance-label");
  const graveyardFeedEl = document.getElementById("graveyard-feed");
  const graveyardEventEl = document.getElementById("graveyard-event");
  const eventStatusEl = document.getElementById("event-status");
  const srStatusEl = document.getElementById("sr-status");
  const aliveCountEl = document.getElementById("alive-count");
  const totalCountEl = document.getElementById("total-count");
  const form = document.getElementById("message-form");
  const input = document.getElementById("message-input");
  const sendButton = document.getElementById("send-button");
  const composerEl = document.getElementById("composer");
  const captionEl = document.getElementById("composer-caption");
  const silenceBlock = document.getElementById("silence-block");
  const silencePoemTextEl = document.getElementById("silence-poem-text");
  const silencePoemDateEl = document.getElementById("silence-poem-date");
  const ashCanvas = document.getElementById("ash-canvas");
  const ashContext = ashCanvas.getContext("2d");
  const worldCanvas = document.getElementById("world-canvas");
  const sacrificeOptionsEl = document.getElementById("sacrifice-options");
  const mutationTitleEl = document.getElementById("mutation-title");
  const mutationConsequenceEl = document.getElementById(
    "mutation-consequence",
  );
  const buildLabelEl = document.getElementById("build-label");
  const compileStatusEl = document.getElementById("compile-status");
  const compileTimeEl = document.getElementById("compile-time");
  const sourceCodeEl = document.getElementById("source-code");
  const editionLabelEl = document.getElementById("edition-label");
  const lineageLabelEl = document.getElementById("lineage-label");
  const archiveLinkEl = document.getElementById("archive-link");
  const closedEditionLabelEl = document.getElementById(
    "closed-edition-label",
  );
  const rebirthLabelEl = document.getElementById("rebirth-label");
  const rebirthCountdownEl = document.getElementById("rebirth-countdown");
  const birthVeilEl = document.getElementById("birth-veil");
  const birthPredecessorEl = document.getElementById("birth-predecessor");
  const birthEditionEl = document.getElementById("birth-edition");
  const birthLineageEl = document.getElementById("birth-lineage");
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

  let currentAlive = null;
  let sending = false;
  let ceremonyInFlight = false;
  let isSilenced = false;
  let ashParticles = [];
  let ashTrails = [];
  let ashFrame = null;
  let graveyardEntries = [];
  let lastGraveSignature = null;
  let lastUtteranceId = null;
  let lastFallbackSignature = null;
  let stateFetchInFlight = false;
  let selectedSacrifice = null;
  let latestWorldVersion = null;
  let latestEditionNumber = null;
  let rebirthClockTimer = null;
  let birthVeilTimer = null;
  let worldEngine = null;
  let worldAudioContext = null;

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
  const defaultCaption = captionEl.textContent;

  function syncComposerState() {
    const busy =
      sending || ceremonyInFlight || isSilenced || !selectedSacrifice;
    sendButton.disabled = busy;
    conversationEl.setAttribute("aria-busy", String(ceremonyInFlight));
  }

  function clearSacrificeSelection() {
    selectedSacrifice = null;
    sacrificeOptionsEl
      ?.querySelectorAll(".sacrifice-option")
      .forEach((button) => {
        button.classList.remove("is-selected");
        button.setAttribute("aria-pressed", "false");
      });
    worldEngine?.clearPreview?.();
    captionEl.textContent = defaultCaption;
    sendButton.textContent = DEFAULT_SEND_LABEL;
    syncComposerState();
  }

  function selectSacrifice(option, button) {
    unlockWorldAudio();
    selectedSacrifice = option;
    const consequence = String(option.consequence || "")
      .replace(/[.!?]+$/, "");
    sacrificeOptionsEl
      .querySelectorAll(".sacrifice-option")
      .forEach((candidate) => {
        const selected = candidate === button;
        candidate.classList.toggle("is-selected", selected);
        candidate.setAttribute("aria-pressed", String(selected));
    });
    worldEngine?.preview?.(option);
    sendButton.textContent = `sacrifice ${option.word} & ask`;
    captionEl.textContent =
      `Erase “${option.word}”: ${consequence}. This choice is permanent.`;
    srStatusEl.textContent =
      `${option.word} selected. ${consequence}. Submit to change the shared world.`;
    syncComposerState();
  }

  function unlockWorldAudio() {
    if (!worldAudioContext) {
      const AudioCtor = window.AudioContext || window.webkitAudioContext;
      if (!AudioCtor) return;
      worldAudioContext = new AudioCtor();
    }
    if (worldAudioContext.state === "suspended") {
      void worldAudioContext.resume();
    }
  }

  function playMutationTone(world) {
    const context = worldAudioContext;
    if (!context || context.state !== "running") return;
    if (Number(world?.genome?.sound ?? 1) <= 0.001) return;
    const now = context.currentTime;
    const word = String(world?.last_word || "absence");
    const seed = [...word].reduce(
      (sum, character) => sum + character.charCodeAt(0),
      0,
    );
    const base = 48 + (seed % 54);
    const gain = context.createGain();
    const filter = context.createBiquadFilter();
    filter.type = "lowpass";
    filter.frequency.setValueAtTime(720, now);
    filter.frequency.exponentialRampToValueAtTime(140, now + 1.45);
    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(0.026, now + 0.08);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + 1.5);
    filter.connect(gain);
    gain.connect(context.destination);

    [1, 1.49, 2.01].forEach((ratio, index) => {
      const oscillator = context.createOscillator();
      oscillator.type = index === 0 ? "sine" : "triangle";
      oscillator.frequency.setValueAtTime(base * ratio * 2.2, now);
      oscillator.frequency.exponentialRampToValueAtTime(
        Math.max(36, base * ratio * 0.72),
        now + 1.45,
      );
      oscillator.connect(filter);
      oscillator.start(now + index * 0.025);
      oscillator.stop(now + 1.55);
    });
  }

  function renderSacrificeOptions(options) {
    if (!sacrificeOptionsEl) return;
    const safeOptions = Array.isArray(options) ? options.slice(0, 3) : [];
    const selectedWord = selectedSacrifice?.word;
    sacrificeOptionsEl.replaceChildren();

    if (safeOptions.length === 0) {
      const empty = document.createElement("p");
      empty.className = "options-loading";
      empty.textContent = "no stable law can be offered right now";
      sacrificeOptionsEl.appendChild(empty);
      selectedSacrifice = null;
      syncComposerState();
      return;
    }

    let selectionStillAlive = false;
    safeOptions.forEach((option) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "sacrifice-option";
      button.setAttribute("aria-pressed", "false");
      button.setAttribute(
        "aria-label",
        `Sacrifice ${option.word}: ${option.consequence}`,
      );

      const word = document.createElement("span");
      word.className = "sacrifice-word";
      word.textContent = option.word;
      const consequence = document.createElement("span");
      consequence.className = "sacrifice-consequence";
      consequence.textContent = option.consequence;
      const preview = document.createElement("span");
      preview.className = "sacrifice-preview";
      preview.textContent =
        typeof option.preview === "string"
          ? option.preview
          : `preview ${option.law || "this absence"}`;
      button.append(word, consequence, preview);

      button.addEventListener("pointerenter", () => {
        if (!sending) worldEngine?.preview?.(option);
      });
      button.addEventListener("pointerleave", () => {
        if (selectedSacrifice) {
          worldEngine?.preview?.(selectedSacrifice);
        } else {
          worldEngine?.clearPreview?.();
        }
      });
      button.addEventListener("focus", () => {
        if (!sending) worldEngine?.preview?.(option);
      });
      button.addEventListener("blur", () => {
        if (selectedSacrifice) {
          worldEngine?.preview?.(selectedSacrifice);
        } else {
          worldEngine?.clearPreview?.();
        }
      });
      button.addEventListener("click", () => selectSacrifice(option, button));

      if (selectedWord && option.word === selectedWord) {
        selectedSacrifice = option;
        selectionStillAlive = true;
        button.classList.add("is-selected");
        button.setAttribute("aria-pressed", "true");
      }
      sacrificeOptionsEl.appendChild(button);
    });

    if (selectedWord && !selectionStillAlive) {
      selectedSacrifice = null;
      worldEngine?.clearPreview?.();
      captionEl.textContent = defaultCaption;
    } else if (selectionStillAlive) {
      worldEngine?.preview?.(selectedSacrifice);
    }
    syncComposerState();
  }

  function visibleShaderSource(source) {
    if (!source) return "// shader source will appear after the first build";
    const lines = String(source).split("\n");
    const exact = lines.filter((line) =>
      /^(?:precision |uniform (?:vec2 uResolution|float uTime|float uPreviewMix|float uImpact)|void main\(\)|\s*(?:fragColor|gl_FragColor)\s*=)/.test(
        line,
      ),
    );
    return (exact.length >= 4 ? exact : lines).slice(0, 12).join("\n");
  }

  function handleWorldCompile(result = {}) {
    const ok = result.ok !== false && result.success !== false;
    compileStatusEl.textContent = ok ? "COMPILE PASS" : "COMPILE FAILED";
    compileStatusEl.classList.toggle("is-pass", ok);
    compileStatusEl.classList.toggle("is-fail", !ok);
    const measured = Number(result.ms ?? result.compileMs);
    compileTimeEl.textContent = Number.isFinite(measured)
      ? `RECOMPILED IN ${Math.max(0.1, measured).toFixed(1)} MS · LIVE FOR EVERY VISITOR`
      : ok
        ? "RECOMPILED LIVE · SHARED WITH EVERY VISITOR"
        : "last successful world remains visible";
    const diff = Array.isArray(result.diffLines)
      ? result.diffLines.slice(0, 4).join("\n")
      : "";
    sourceCodeEl.textContent = [diff, visibleShaderSource(result.source)]
      .filter(Boolean)
      .join("\n\n");
  }

  function applyWorldState(world, { remote = false } = {}) {
    if (!world) return;
    const version = Number(world.version || 0);
    const initial = latestWorldVersion === null;
    const changed =
      latestWorldVersion !== null && version !== latestWorldVersion;
    buildLabelEl.textContent = `BUILD ${String(version).padStart(4, "0")}`;

    if (world.last_word) {
      mutationTitleEl.textContent =
        `${String(world.last_word).toUpperCase()} WAS FORGOTTEN`;
      mutationConsequenceEl.textContent =
        world.last_consequence || "the world rebuilt around the absence";
    }

    if (changed) {
      document.body.classList.remove("is-mutating");
      requestAnimationFrame(() => document.body.classList.add("is-mutating"));
      setTimeout(() => document.body.classList.remove("is-mutating"), 900);
      if (remote) {
        srStatusEl.textContent =
          `Another visitor erased ${world.last_word}. ${world.last_consequence || ""}`;
      }
      playMutationTone(world);
    }
    latestWorldVersion = version;
    if (initial || changed) {
      worldEngine?.apply?.(world);
    }
  }

  // ------------------------------------------------------------- editions

  function shortLineage(seed) {
    return String(seed || "00000000")
      .replace(/[^a-f0-9]/gi, "")
      .slice(0, 8)
      .padEnd(8, "0")
      .toUpperCase();
  }

  function applyLineageVisual(edition) {
    const compact = shortLineage(edition?.lineage_seed);
    const numeric = Number.parseInt(compact, 16) || 0;
    const angle = numeric % 360;
    const offsetX = 36 + ((numeric >>> 8) % 28);
    const offsetY = 39 + ((numeric >>> 16) % 24);
    document.body.style.setProperty("--lineage-angle", `${angle}deg`);
    document.body.style.setProperty("--lineage-x", `${offsetX}%`);
    document.body.style.setProperty("--lineage-y", `${offsetY}%`);
    document.body.dataset.lineage = compact;
    if (lineageLabelEl) {
      lineageLabelEl.textContent =
        `${Number(edition?.number || 1) === 1 ? "ORIGIN" : "INHERITED SCAR"} · ${compact}`;
    }
  }

  function restoreLivingUI() {
    if (rebirthClockTimer) {
      clearInterval(rebirthClockTimer);
      rebirthClockTimer = null;
    }
    isSilenced = false;
    composerEl.classList.remove("silenced");
    silenceBlock.classList.add("hidden");
    silencePoemTextEl.textContent = "";
    silencePoemDateEl.textContent = "";
    syncComposerState();
  }

  function resetConversationForBirth(editionLabel) {
    conversationEl.replaceChildren();
    waitingLineEl = document.createElement("p");
    waitingLineEl.id = "waiting-line";
    waitingLineEl.className = "waiting-line";
    waitingLineEl.textContent =
      `${editionLabel} has no memories yet. Its first absence is yours to choose.`;
    conversationEl.appendChild(waitingLineEl);
    stageLabelEl.textContent = "a new world listens";
    eventStatusEl.textContent = "";
    lastUtteranceId = null;
    lastFallbackSignature = null;
    lastGraveSignature = null;
  }

  function announceBirth(edition, predecessor) {
    if (!birthVeilEl) return;
    const label = edition?.label || `WORLD ${edition?.number || ""}`;
    const previousLabel =
      predecessor?.label ||
      `WORLD ${Math.max(1, Number(edition?.number || 2) - 1)
        .toString()
        .padStart(3, "0")}`;
    birthPredecessorEl.textContent = `${previousLabel} REMAINS CLOSED`;
    birthEditionEl.textContent = label;
    birthLineageEl.textContent =
      `INHERITED SCAR · ${shortLineage(edition?.lineage_seed)}`;
    birthVeilEl.classList.remove("hidden");
    document.body.classList.add("is-being-born");
    if (birthVeilTimer) clearTimeout(birthVeilTimer);
    birthVeilTimer = setTimeout(
      () => {
        birthVeilEl.classList.add("is-leaving");
        setTimeout(() => {
          birthVeilEl.classList.add("hidden");
          birthVeilEl.classList.remove("is-leaving");
          document.body.classList.remove("is-being-born");
        }, reduceMotion.matches ? 20 : 1100);
      },
      reduceMotion.matches ? 900 : 4600,
    );
  }

  function applyEditionState(edition, archives = [], archiveCount = null) {
    if (!edition) return false;
    const number = Math.max(1, Number(edition.number || 1));
    const label = edition.label || `WORLD ${String(number).padStart(3, "0")}`;
    const previousNumber = latestEditionNumber;
    const changed =
      previousNumber !== null && Number(previousNumber) !== Number(number);
    const safeArchives = Array.isArray(archives) ? archives : [];
    const totalArchives = Number.isFinite(Number(archiveCount))
      ? Math.max(0, Number(archiveCount))
      : safeArchives.length;

    if (editionLabelEl) editionLabelEl.textContent = label;
    if (archiveLinkEl) {
      archiveLinkEl.textContent =
        `archive / ${totalArchives} →`;
      archiveLinkEl.setAttribute(
        "aria-label",
        `${totalArchives} immutable world editions`,
      );
    }
    applyLineageVisual(edition);

    if (changed) {
      const predecessor =
        safeArchives.find((item) => Number(item.number) === previousNumber) ||
        safeArchives[0] ||
        null;
      latestWorldVersion = null;
      selectedSacrifice = null;
      currentAlive = null;
      graveyardEntries = [];
      graveyardFeedEl.replaceChildren();
      graveyardEventEl.textContent = "";
      resetConversationForBirth(label);
      restoreLivingUI();
      mutationTitleEl.textContent = `${label} WAS BORN`;
      mutationConsequenceEl.textContent =
        `${predecessor?.label || "The previous world"} remains closed. This body inherited scar ${shortLineage(edition?.lineage_seed)}.`;
      announceBirth(edition, predecessor);
      srStatusEl.textContent =
        `${label} has been born. ${predecessor?.label || "The previous world"} remains archived.`;
    }

    latestEditionNumber = number;
    return changed;
  }

  function clearReturnSelection() {
    delete input.dataset.returningWord;
    composerEl.classList.remove("has-return-word");
    captionEl.textContent = defaultCaption;
  }

  function selectDeadWord(word) {
    input.value = word;
    input.dataset.returningWord = word.toLowerCase();
    composerEl.classList.add("has-return-word");
    captionEl.textContent = `“${word}” will return when you send.`;
    eventStatusEl.textContent = `${word} is ready to be returned`;
    srStatusEl.textContent = `${word} selected. Send to return it.`;
    input.focus();
  }

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

  // ------------------------------------------------------- funeral particles

  function sizeAshCanvas() {
    const ratio = Math.min(2, window.devicePixelRatio || 1);
    ashCanvas.width = Math.round(window.innerWidth * ratio);
    ashCanvas.height = Math.round(window.innerHeight * ratio);
    ashCanvas.style.width = `${window.innerWidth}px`;
    ashCanvas.style.height = `${window.innerHeight}px`;
    ashContext.setTransform(ratio, 0, 0, ratio, 0, 0);
  }

  function quadraticPoint(start, control, end, t) {
    const inverse = 1 - t;
    return {
      x:
        inverse * inverse * start.x +
        2 * inverse * t * control.x +
        t * t * end.x,
      y:
        inverse * inverse * start.y +
        2 * inverse * t * control.y +
        t * t * end.y,
    };
  }

  function drawAsh(now) {
    ashContext.clearRect(0, 0, window.innerWidth, window.innerHeight);
    ashContext.globalCompositeOperation = "lighter";

    ashTrails = ashTrails.filter((trail) => {
      const elapsed = now - trail.startedAt;
      if (elapsed < 0) return true;
      const drawProgress = Math.min(1, elapsed / 520);
      const fadeProgress = Math.max(0, (elapsed - 850) / 2700);
      const alpha = Math.max(0, 1 - fadeProgress);
      const steps = Math.max(2, Math.round(28 * drawProgress));

      function strokeTrail(width, color, blur) {
        ashContext.beginPath();
        ashContext.moveTo(trail.start.x, trail.start.y);
        for (let step = 1; step <= steps; step += 1) {
          const point = quadraticPoint(
            trail.start,
            trail.control,
            trail.end,
            (step / steps) * drawProgress,
          );
          ashContext.lineTo(point.x, point.y);
        }
        ashContext.lineWidth = width;
        ashContext.strokeStyle = color;
        ashContext.shadowColor = "rgba(255, 77, 28, 0.8)";
        ashContext.shadowBlur = blur;
        ashContext.stroke();
      }

      strokeTrail(3.2, `rgba(255, 69, 24, ${alpha * 0.12})`, 22);
      strokeTrail(0.75, `rgba(255, 135, 77, ${alpha * 0.55})`, 7);

      const leading = quadraticPoint(
        trail.start,
        trail.control,
        trail.end,
        drawProgress,
      );
      ashContext.beginPath();
      ashContext.arc(leading.x, leading.y, 2.4, 0, Math.PI * 2);
      ashContext.fillStyle = `rgba(255, 219, 180, ${alpha * 0.78})`;
      ashContext.shadowBlur = 12;
      ashContext.fill();
      ashContext.shadowBlur = 0;
      return elapsed < 3550;
    });

    ashParticles = ashParticles.filter((particle) => {
      const elapsed = now - particle.startedAt - particle.delay;
      if (elapsed < 0) return true;
      const progress = Math.min(1, elapsed / particle.duration);
      const eased = 1 - Math.pow(1 - progress, 2.4);
      const point = quadraticPoint(
        particle.start,
        particle.control,
        particle.end,
        eased,
      );
      const previous = quadraticPoint(
        particle.start,
        particle.control,
        particle.end,
        Math.max(0, eased - 0.035),
      );
      const alpha = Math.sin(Math.PI * progress) * particle.alpha;

      ashContext.beginPath();
      ashContext.moveTo(previous.x, previous.y);
      ashContext.lineTo(point.x, point.y);
      ashContext.strokeStyle = `rgba(255, 103, 54, ${alpha * 0.42})`;
      ashContext.lineWidth = particle.size * 0.8;
      ashContext.stroke();

      ashContext.beginPath();
      ashContext.arc(point.x, point.y, particle.size, 0, Math.PI * 2);
      ashContext.fillStyle = `rgba(255, 119, 66, ${alpha})`;
      ashContext.shadowColor = "rgba(255, 86, 38, 0.8)";
      ashContext.shadowBlur = 8;
      ashContext.fill();
      ashContext.shadowBlur = 0;
      return progress < 1;
    });
    ashContext.globalCompositeOperation = "source-over";

    if (ashParticles.length > 0 || ashTrails.length > 0) {
      ashFrame = requestAnimationFrame(drawAsh);
    } else {
      ashFrame = null;
      ashContext.clearRect(0, 0, window.innerWidth, window.innerHeight);
    }
  }

  function graveTargetFor(word) {
    if (document.body.classList.contains("world-body") && worldCanvas) {
      const worldRect = worldCanvas.getBoundingClientRect();
      const wordHash = [...word].reduce(
        (sum, character) => sum + character.charCodeAt(0),
        0,
      );
      return {
        x: worldRect.left + worldRect.width * (0.48 + (wordHash % 17) / 100),
        y: worldRect.top + worldRect.height * (0.38 + (wordHash % 23) / 120),
      };
    }
    const normalized = word.toLowerCase();
    const candidates = graveyardFeedEl.querySelectorAll("[data-word]");
    for (const candidate of candidates) {
      if (candidate.dataset.word === normalized) {
        const rect = candidate.getBoundingClientRect();
        return {
          x: rect.left + Math.min(30, rect.width * 0.35),
          y: rect.top + rect.height * 0.55,
        };
      }
    }
    const panelRect = graveyardFeedEl.getBoundingClientRect();
    return {
      x: panelRect.left + 18,
      y: panelRect.top + Math.min(110, panelRect.height * 0.35),
    };
  }

  function releaseWord(span, word) {
    if (reduceMotion.matches) return;
    const compactMotion = window.innerWidth < 620;
    const rect = span.getBoundingClientRect();
    const start = {
      x: rect.left + rect.width * 0.55,
      y: rect.top + rect.height * 0.55,
    };
    const end = graveTargetFor(word);
    const now = performance.now();
    const direction = end.x >= start.x ? 1 : -1;
    const control = {
      x: start.x + (end.x - start.x) * 0.5,
      y: Math.min(start.y, end.y) - 95,
    };
    ashTrails.push({
      start,
      control,
      end,
      startedAt: now,
    });

    const particleCount = compactMotion ? 20 : 46;
    const particleCenter = (particleCount - 1) / 2;
    for (let i = 0; i < particleCount; i += 1) {
      const spread = (i - particleCenter) / Math.max(1, particleCenter);
      ashParticles.push({
        start: {
          x: start.x + spread * Math.max(8, rect.width * 0.45),
          y: start.y + Math.sin(i * 1.7) * 5,
        },
        control: {
          x: control.x + Math.sin(i * 1.3) * 18,
          y:
            control.y -
            Math.abs(spread) * 42 +
            Math.sin(i) * 18,
        },
        end: {
          x: end.x + direction * (i % 4) * 2,
          y: end.y + spread * 8,
        },
        startedAt: now,
        delay: (i % 11) * 34,
        duration: 1450 + (i % 7) * 125,
        size: 0.72 + (i % 5) * 0.36,
        alpha: 0.46 + (i % 6) * 0.075,
      });
    }

    if (!ashFrame) {
      ashFrame = requestAnimationFrame(drawAsh);
    }
  }

  function announceDeath(word) {
    const message = `${word} died just now`;
    eventStatusEl.textContent = message;
    graveyardEventEl.textContent = message;
  }

  function stageGraveArrival(word, { reuseExisting = false } = {}) {
    if (reuseExisting) {
      const normalized = word.toLowerCase();
      const existingWord = [
        ...graveyardFeedEl.querySelectorAll("[data-word]"),
      ].find((candidate) => candidate.dataset.word === normalized);
      if (existingWord) {
        const existingRow = existingWord.closest(".grave-entry");
        if (existingRow) {
          existingRow.classList.add("is-crossing");
          setTimeout(() => existingRow.classList.remove("is-crossing"), 3400);
        }
        return;
      }
    }

    const row = document.createElement("div");
    row.className = "grave-entry is-latest is-arrival is-crossing";
    row.dataset.key = `crossing:${word}:${performance.now()}`;

    const wordSpan = document.createElement("span");
    wordSpan.className = "grave-word burned";
    wordSpan.dataset.word = word.toLowerCase();
    wordSpan.textContent = word;

    const tsSpan = document.createElement("span");
    tsSpan.className = "grave-ts";
    tsSpan.textContent = "crossing";

    graveyardFeedEl
      .querySelectorAll(".is-latest")
      .forEach((entry) => entry.classList.remove("is-latest"));
    row.appendChild(wordSpan);
    row.appendChild(tsSpan);
    graveyardFeedEl.prepend(row);
    while (graveyardFeedEl.children.length > MAX_VISIBLE_GRAVES + 3) {
      graveyardFeedEl.lastElementChild.remove();
    }
  }

  // -------------------------------------------------------------- messages

  function scrollToBottom() {
    conversationEl.scrollTop = conversationEl.scrollHeight;
  }

  function coreWordOf(str) {
    const match = str.toLowerCase().match(/[a-z']+/);
    if (!match) return null;
    let word = match[0];
    if (word.endsWith("'s")) word = word.slice(0, -2);
    word = word.replace(/^'+|'+$/g, "");
    return word || null;
  }

  function retireOlderMessages() {
    const messages = conversationEl.querySelectorAll(".msg");
    messages.forEach((message) => message.classList.add("is-previous"));
    if (messages.length > 5) {
      for (let i = 0; i < messages.length - 5; i += 1) {
        messages[i].remove();
      }
    }
  }

  function revealStage() {
    if (waitingLineEl) waitingLineEl.classList.add("hidden");
  }

  function addUserMessage(text) {
    revealStage();
    retireOlderMessages();
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
    const returned = revivedWords.join(", ");
    eventStatusEl.textContent = `${returned} returned by a visitor`;
    graveyardEventEl.textContent = `${returned} returned by a visitor`;
    srStatusEl.textContent = `${returned} returned to the being`;
  }

  function escapeHtml(s) {
    const div = document.createElement("div");
    div.textContent = s;
    return div.innerHTML;
  }

  // Render an AI message word-by-word (typewriter), showing ghost segments
  // as ember gaps. `segments` is [{t:'w', s:'hello'}|{t:'x'}].
  // `burnedNow` is the list of words that got burned by this exact reply,
  // used to stage a small funeral for each word after the reply is complete.
  function addAiMessageAnimated(
    segments,
    burnedNow,
    { replay = false, onFuneralStart = null } = {},
  ) {
    ceremonyInFlight = true;
    syncComposerState();
    revealStage();
    retireOlderMessages();
    stageLabelEl.textContent = "the last thing it said";
    const wrap = document.createElement("div");
    wrap.className = "msg ai";
    if (replay) wrap.classList.add("is-replay");
    const spokenText = segments
      .map((segment) =>
        segment.t === "x" ? "a word it can no longer speak" : segment.s,
      )
      .join(" ");
    const accessibleLine = document.createElement("span");
    accessibleLine.className = "sr-only";
    accessibleLine.textContent = spokenText;
    const line = document.createElement("div");
    line.className = "msg-line";
    line.setAttribute("aria-hidden", "true");
    wrap.appendChild(accessibleLine);
    wrap.appendChild(line);
    conversationEl.appendChild(wrap);
    scrollToBottom();

    const burnedSet = new Set((burnedNow || []).map((w) => w.toLowerCase()));
    const queuedFunerals = new Set();
    const funeralWords = [];
    const cursor = document.createElement("span");
    cursor.className = "typing-cursor";
    cursor.textContent = "▍";
    line.appendChild(cursor);

    let i = 0;

    function beginFuneral(resolve) {
      if (typeof onFuneralStart === "function") onFuneralStart();
      const stageRect = conversationEl.getBoundingClientRect();
      const onScreenFunerals = funeralWords.filter(({ span }) => {
        const rect = span.getBoundingClientRect();
        return rect.bottom >= stageRect.top && rect.top <= stageRect.bottom;
      });
      const candidates =
        onScreenFunerals.length > 0 ? onScreenFunerals : funeralWords;
      const visibleFunerals = candidates.slice(-MAX_VISIBLE_FUNERALS);
      const visibleSpans = new Set(visibleFunerals.map(({ span }) => span));
      visibleFunerals.forEach(({ span, word }, index) => {
        const delay = reduceMotion.matches
          ? index * 30
          : 520 + index * FUNERAL_STAGGER_MS;
        setTimeout(() => {
          span.classList.add("is-dying");
          announceDeath(word);
          stageGraveArrival(word, { reuseExisting: replay });
          requestAnimationFrame(() => releaseWord(span, word));
          setTimeout(() => {
            span.classList.remove("is-dying");
            span.classList.add("is-dead");
          }, reduceMotion.matches ? 80 : 1650);
        }, delay);
      });
      funeralWords
        .filter(({ span }) => !visibleSpans.has(span))
        .forEach(({ span }) => span.classList.add("is-dead"));
      const finalDelay =
        visibleFunerals.length === 0
          ? 0
          : (reduceMotion.matches ? visibleFunerals.length * 30 : 520 +
              (visibleFunerals.length - 1) * FUNERAL_STAGGER_MS) +
            (reduceMotion.matches ? 100 : 1750);
      setTimeout(() => {
        if (visibleFunerals.length > 0) {
          const lostWords = visibleFunerals.map(({ word }) => word).join(", ");
          srStatusEl.textContent = `The being lost: ${lostWords}`;
        }
        resolve();
      }, finalDelay);
    }

    return new Promise((resolve) => {
      function renderNext() {
        if (i >= segments.length) {
          cursor.remove();
          wrap.classList.add("is-complete");
          srStatusEl.textContent = `It said: ${spokenText}`;
          scrollToBottom();
          beginFuneral(resolve);
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
          span.setAttribute("aria-label", "a word it can no longer speak");
          span.textContent = "···";
          line.insertBefore(span, cursor);
        } else {
          const span = document.createElement("span");
          span.className = "word";
          span.textContent = seg.s;
          const core = coreWordOf(seg.s);
          if (
            core &&
            burnedSet.has(core) &&
            !queuedFunerals.has(core)
          ) {
            span.dataset.word = core;
            funeralWords.push({ span, word: core });
            queuedFunerals.add(core);
          }
          line.insertBefore(span, cursor);
        }

        scrollToBottom();
        setTimeout(
          renderNext,
          reduceMotion.matches ? 0 : TYPE_MS_PER_WORD,
        );
      }

      renderNext();
    }).finally(() => {
      ceremonyInFlight = false;
      syncComposerState();
    });
  }

  function addSystemLine(text) {
    revealStage();
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

  function updateRebirthClock(edition) {
    if (!rebirthCountdownEl || !rebirthLabelEl) return;
    if (rebirthClockTimer) {
      clearInterval(rebirthClockTimer);
      rebirthClockTimer = null;
    }
    const nextNumber = Math.max(1, Number(edition?.number || 1) + 1);
    const nextLabel = `WORLD ${String(nextNumber).padStart(3, "0")}`;
    rebirthLabelEl.textContent =
      `${nextLabel} is forming from these remains`;

    const target = Date.parse(edition?.rebirth_at || "");
    const render = () => {
      const remaining = Number.isFinite(target)
        ? Math.max(0, (target - Date.now()) / 1000)
        : Math.max(0, Number(edition?.rebirth_in_seconds || 0));
      const seconds = Math.ceil(remaining);
      rebirthCountdownEl.textContent =
        seconds > 0 ? `00:${String(seconds).padStart(2, "0")}` : "BIRTH";
      if (seconds <= 0 && rebirthClockTimer) {
        clearInterval(rebirthClockTimer);
        rebirthClockTimer = null;
      }
    };
    render();
    if (Number.isFinite(target) && target > Date.now()) {
      rebirthClockTimer = setInterval(render, 250);
    }
  }

  function applySilencedUI(poem, silencedAt, edition) {
    isSilenced = true;
    syncComposerState();
    composerEl.classList.add("silenced");
    silenceBlock.classList.remove("hidden");
    if (closedEditionLabelEl) {
      closedEditionLabelEl.textContent =
        `${edition?.label || "THIS WORLD"} / CLOSED`;
    }
    if (poem) silencePoemTextEl.textContent = poem;
    if (silencedAt) silencePoemDateEl.textContent = formatDate(silencedAt);
    updateRebirthClock(edition);
  }

  // -------------------------------------------------------------- graveyard

  function graveEntryKey(entry, index) {
    return entry.id !== undefined
      ? `event:${entry.id}`
      : `${entry.ts || "undated"}:${entry.kind || "unknown"}:${entry.word}:${index}`;
  }

  function buildGraveEntry(entry) {
    const row = document.createElement("div");
    row.className = "grave-entry";

    const wordSpan =
      entry.kind === "burn"
        ? document.createElement("button")
        : document.createElement("span");
    wordSpan.className = "grave-word";
    if (entry.kind === "burn") {
      wordSpan.classList.add("burned");
      wordSpan.type = "button";
      wordSpan.addEventListener("click", () => {
        const word = wordSpan.dataset.wordLabel;
        selectDeadWord(word);
      });
    }

    const tsSpan = document.createElement("span");
    tsSpan.className = "grave-ts";

    row.appendChild(wordSpan);
    row.appendChild(tsSpan);
    return row;
  }

  function updateGraveEntry(row, entry, index) {
    row.classList.toggle("is-latest", index === 0);
    const wordSpan = row.querySelector(".grave-word");
    const tsSpan = row.querySelector(".grave-ts");

    wordSpan.className = "grave-word";
    if (entry.kind === "burn") {
      wordSpan.classList.add("burned");
      wordSpan.textContent = entry.word;
      wordSpan.dataset.word = entry.word.toLowerCase();
      wordSpan.dataset.wordLabel = entry.word;
      wordSpan.title = `Return “${entry.word}” to the being`;
      wordSpan.setAttribute(
        "aria-label",
        `Return the dead word ${entry.word} to the being`,
      );
    } else if (entry.kind === "ghost") {
      wordSpan.classList.add("ghost");
      wordSpan.textContent = "···";
      wordSpan.title = entry.word;
    } else if (entry.kind === "revive") {
      wordSpan.classList.add("revived");
      wordSpan.textContent = entry.word;
    } else {
      wordSpan.textContent = entry.word;
    }
    tsSpan.textContent = entry.relative || "";
  }

  function renderGraveyard(entries) {
    graveyardEntries = entries.slice(0, MAX_VISIBLE_GRAVES);
    const wasEmpty = graveyardFeedEl.children.length === 0;
    const existing = new Map(
      [...graveyardFeedEl.children].map((row) => [row.dataset.key, row]),
    );

    graveyardEntries.forEach((e, index) => {
      const key = graveEntryKey(e, index);
      let row = existing.get(key);
      if (!row) {
        row = buildGraveEntry(e);
        row.dataset.key = key;
        if (!wasEmpty) {
          row.classList.add("is-arrival");
          row.addEventListener(
            "animationend",
            () => row.classList.remove("is-arrival"),
            { once: true },
          );
        }
      }
      updateGraveEntry(row, e, index);
      graveyardFeedEl.appendChild(row);
      existing.delete(key);
    });
    existing.forEach((row) => row.remove());

    if (graveyardEntries.length > 0) {
      const latest = graveyardEntries[0];
      const signature = `${latest.ts || ""}:${latest.kind}:${latest.word}`;
      const verb =
        latest.kind === "revive"
          ? "returned"
          : latest.kind === "ghost"
            ? "was reached for"
            : "died";
      if (signature !== lastGraveSignature) {
        graveyardEventEl.textContent =
          `${latest.word} ${verb} ${latest.relative || "just now"}`;
        lastGraveSignature = signature;
      }
    }
  }

  function replayLatestLoss(entries) {
    const latestBurn = entries.find((entry) => entry.kind === "burn");
    if (!latestBurn) return;
    const signature = `${latestBurn.ts || ""}:${latestBurn.word}`;
    if (signature === lastFallbackSignature) return;
    lastFallbackSignature = signature;

    revealStage();
    stageLabelEl.textContent = "the latest word it lost";
    const wrap = document.createElement("div");
    wrap.className = "loss-replay";
    const word = document.createElement("span");
    word.className = "loss-replay-word";
    word.textContent = latestBurn.word;
    wrap.appendChild(word);
    conversationEl.appendChild(wrap);
    eventStatusEl.textContent =
      `${latestBurn.word} died ${latestBurn.relative || "just now"}`;

    setTimeout(() => {
      word.classList.add("is-dying");
      releaseWord(word, latestBurn.word);
      setTimeout(
        () => word.classList.add("is-dead"),
        reduceMotion.matches ? 80 : 1650,
      );
    }, reduceMotion.matches ? 0 : 650);
  }

  // ------------------------------------------------------------------ API

  async function fetchState() {
    if (stateFetchInFlight) return null;
    stateFetchInFlight = true;
    try {
      const res = await fetch("/api/state");
      if (!res.ok) return null;
      const data = await res.json();
      applyEditionState(data.edition, data.archives, data.archive_count);
      updateCounters(data.alive, data.total);
      const remoteWorldChange =
        latestWorldVersion !== null &&
        Number(data.world?.version || 0) !== latestWorldVersion;
      applyWorldState(data.world, { remote: remoteWorldChange });
      renderSacrificeOptions(data.sacrifice_options || []);
      renderGraveyard(data.graveyard || []);
      if (data.silenced) {
        applySilencedUI(data.poem, data.silenced_at, data.edition);
      } else if (
        data.latest_utterance &&
        data.latest_utterance.id !== lastUtteranceId
      ) {
        const isRemoteArrival = lastUtteranceId !== null;
        lastUtteranceId = data.latest_utterance.id;
        if (isRemoteArrival) {
          const message = "another visitor changed what it can say";
          eventStatusEl.textContent = message;
          graveyardEventEl.textContent = message;
          srStatusEl.textContent = message;
        }
        await addAiMessageAnimated(
          data.latest_utterance.segments || [],
          data.latest_utterance.burned_now || [],
          { replay: true },
        );
      } else if (!data.latest_utterance && lastUtteranceId === null) {
        replayLatestLoss(data.graveyard || []);
      }
      return data;
    } catch (e) {
      console.warn("LAST WORDS state sync failed", e);
      return null;
    } finally {
      stateFetchInFlight = false;
    }
  }

  async function handleReplyPayload(data) {
    applyEditionState(data.edition, data.archives, data.archive_count);
    if (data.silenced) {
      // Either this call just triggered the ending, or the being was
      // already silent — either way, no more animated replies, just the poem.
      if (data.alive !== undefined) updateCounters(data.alive, data.total);
      applySilencedUI(data.poem, data.silenced_at, data.edition);
      fetchState();
      return;
    }

    if (data.rate_limited) {
      if (data.alive !== undefined) updateCounters(data.alive, data.total);
      addSystemLine(data.system_message || "(it remains quiet)");
      return;
    }

    if (data.world) {
      applyWorldState(data.world);
    }
    if (Array.isArray(data.sacrifice_options)) {
      renderSacrificeOptions(data.sacrifice_options);
    }
    if (data.sacrificed?.word) {
      eventStatusEl.textContent =
        `${data.sacrificed.word} was removed from the world`;
    }

    if (data.utterance_id !== undefined) {
      lastUtteranceId = data.utterance_id;
    }
    await addAiMessageAnimated(
      data.segments || [],
      data.burned_now || [],
      {
        onFuneralStart: () => {
          if (data.alive !== undefined) {
            updateCounters(data.alive, data.total);
          }
        },
      },
    );
    await fetchState();
  }

  async function sendMessage(text) {
    if (sending || !selectedSacrifice) return;
    const sacrificeWord = selectedSacrifice.word;
    sending = true;
    syncComposerState();

    const userWrap = addUserMessage(text);

    try {
      const res = await fetch("/api/message", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text,
          session_id: sessionId,
          sacrifice_word: sacrificeWord,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        addSystemLine(
          data.system_message ||
            data.detail ||
            "(someone else changed that law first — choose again)",
        );
        clearSacrificeSelection();
        await fetchState();
        return;
      }
      clearSacrificeSelection();
      addReviveLine(userWrap, data.revived);
      await handleReplyPayload(data);
    } catch (e) {
      addSystemLine("(the words did not reach it)");
    } finally {
      sending = false;
      syncComposerState();
    }
  }

  // ------------------------------------------------------------------ init

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    if (isSilenced || sending || ceremonyInFlight) return;
    const text = input.value.trim();
    if (!text || !selectedSacrifice) {
      if (!selectedSacrifice) {
        captionEl.textContent = "Choose one law below before the world can answer.";
        srStatusEl.textContent = "Choose one word to sacrifice first.";
      }
      return;
    }
    input.value = "";
    clearReturnSelection();
    sendMessage(text);
  });

  input.addEventListener("input", () => {
    const selected = input.dataset.returningWord;
    if (selected && input.value.trim().toLowerCase() !== selected) {
      clearReturnSelection();
    }
  });

  sizeAshCanvas();
  window.addEventListener("resize", sizeAshCanvas, { passive: true });

  (async () => {
    if (worldCanvas && window.LastWordsWorld?.mount) {
      try {
        worldEngine = window.LastWordsWorld.mount(worldCanvas, {
          onCompile: handleWorldCompile,
        });
        worldCanvas.addEventListener(
          "pointermove",
          (event) => {
            const rect = worldCanvas.getBoundingClientRect();
            worldEngine?.setPointer?.(
              (event.clientX - rect.left) / Math.max(1, rect.width),
              (event.clientY - rect.top) / Math.max(1, rect.height),
            );
          },
          { passive: true },
        );
        worldCanvas.addEventListener(
          "pointerleave",
          () => worldEngine?.setPointer?.(0.5, 0.5),
          { passive: true },
        );
      } catch (error) {
        compileStatusEl.textContent = "VISUAL FALLBACK";
        compileStatusEl.classList.add("is-fail");
        compileTimeEl.textContent = "the world kept its last visible form";
      }
    }
    await fetchState();
    setInterval(() => {
      if (!sending) void fetchState();
    }, STATE_POLL_MS);
  })();
})();
