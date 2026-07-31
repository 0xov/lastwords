/*
 * LAST WORDS — A SELF-ERASING WORLD
 *
 * A dependency-free WebGL artwork engine. The committed genome is baked into
 * authentic GLSL source on every apply(), then compiled and linked for real.
 * preview() only changes uniforms, so hovering a possible mutation never
 * commits a version or spends another compile.
 */
(function installLastWordsWorld(global) {
  "use strict";

  const GENOME_KEYS = [
    "gravity",
    "memory",
    "attraction",
    "turbulence",
    "tempo",
    "light",
    "spectrum",
    "symmetry",
    "cohesion",
    "drift",
    "fracture",
    "touch",
    "sound",
    "depth",
    "scale",
    "elasticity",
    "decay",
    "continuity",
    "temperature",
    "agency",
  ];

  const DEFAULT_GENOME = Object.freeze({
    gravity: 0.78,
    memory: 0.92,
    attraction: 0.66,
    turbulence: 0.42,
    tempo: 0.58,
    light: 0.84,
    spectrum: 0.9,
    symmetry: 0.72,
    cohesion: 0.81,
    drift: 0.25,
    fracture: 0.16,
    touch: 0.7,
    sound: 0.64,
    depth: 0.76,
    scale: 0.55,
    elasticity: 0.68,
    decay: 0.31,
    continuity: 0.88,
    temperature: 0.57,
    agency: 0.74,
  });

  const BONE = "0.88, 0.845, 0.765";
  const EMBER = "1.0, 0.255, 0.105";
  const COOL = "0.285, 0.455, 0.52";
  const BACKGROUND = "#080807";

  let activeWorld = null;

  function clamp01(value) {
    return Math.max(0, Math.min(1, value));
  }

  function copyGenome(genome) {
    const copy = {};
    GENOME_KEYS.forEach((key) => {
      copy[key] = genome[key];
    });
    return copy;
  }

  function finiteGenomeValue(raw, fallback) {
    let value = raw;
    if (value && typeof value === "object") {
      if (Number.isFinite(Number(value.to))) value = value.to;
      else if (Number.isFinite(Number(value.value))) value = value.value;
    }
    value = Number(value);
    if (!Number.isFinite(value)) return fallback;
    if (Math.abs(value) > 1) value /= 100;
    return clamp01(value);
  }

  function genomeSource(input) {
    if (!input || typeof input !== "object") return {};
    if (input.genome && typeof input.genome === "object") return input.genome;
    if (input.worldGenome && typeof input.worldGenome === "object") {
      return input.worldGenome;
    }
    if (input.world_genome && typeof input.world_genome === "object") {
      return input.world_genome;
    }
    if (input.values && typeof input.values === "object") return input.values;
    if (input.preview && typeof input.preview === "object") return input.preview;
    if (input.world && typeof input.world === "object") {
      return genomeSource(input.world);
    }
    return input;
  }

  function normalizeGenome(input, base) {
    const startingPoint = base || DEFAULT_GENOME;
    const next = copyGenome(startingPoint);
    const source = genomeSource(input);

    GENOME_KEYS.forEach((key) => {
      if (Object.prototype.hasOwnProperty.call(source, key)) {
        next[key] = finiteGenomeValue(source[key], next[key]);
      }
    });

    if (
      input &&
      typeof input === "object" &&
      GENOME_KEYS.includes(input.parameter)
    ) {
      const key = input.parameter;
      if (Number.isFinite(Number(input.delta))) {
        next[key] = clamp01(next[key] + Number(input.delta));
      } else {
        next[key] = finiteGenomeValue(input.to ?? input.value, next[key]);
      }
    }

    const changes =
      input && typeof input === "object" && input.changes
        ? input.changes
        : input && typeof input === "object" && input.deltas
          ? input.deltas
          : null;
    if (changes && typeof changes === "object") {
      GENOME_KEYS.forEach((key) => {
        if (!Object.prototype.hasOwnProperty.call(changes, key)) return;
        const change = changes[key];
        if (
          change &&
          typeof change === "object" &&
          Number.isFinite(Number(change.delta))
        ) {
          next[key] = clamp01(next[key] + Number(change.delta));
        } else {
          next[key] = finiteGenomeValue(change, next[key]);
        }
      });
    }

    return next;
  }

  function formatFloat(value) {
    return Number(value).toFixed(6);
  }

  function genomeDiff(previous, next) {
    const lines = [];
    GENOME_KEYS.forEach((key) => {
      const after = next[key];
      const before = previous ? previous[key] : null;
      if (before === null || Math.abs(before - after) > 0.0000005) {
        const constant = `G_${key.toUpperCase()}`;
        if (before === null) {
          lines.push(`+ const float ${constant} = ${formatFloat(after)};`);
        } else {
          lines.push(
            `~ const float ${constant} = ${formatFloat(after)}; // was ${formatFloat(before)}`,
          );
        }
      }
    });
    return lines.length ? lines : ["  // genome unchanged"];
  }

  function genomesDiffer(previous, next) {
    if (!previous) return false;
    return GENOME_KEYS.some(
      (key) => Math.abs(previous[key] - next[key]) > 0.0000005,
    );
  }

  function safeNotify(callback, payload) {
    if (typeof callback !== "function") return;
    try {
      callback(payload);
    } catch (_error) {
      // Artwork rendering must not fail because an inspector callback failed.
    }
  }

  function nowMs() {
    return global.performance && typeof global.performance.now === "function"
      ? global.performance.now()
      : Date.now();
  }

  function motionQuery() {
    if (typeof global.matchMedia !== "function") return null;
    return global.matchMedia("(prefers-reduced-motion: reduce)");
  }

  function createResizeController(canvas, resize) {
    let observer = null;
    const onWindowResize = () => resize();

    if (typeof global.ResizeObserver === "function") {
      observer = new global.ResizeObserver(resize);
      observer.observe(canvas);
    } else if (typeof global.addEventListener === "function") {
      global.addEventListener("resize", onWindowResize, { passive: true });
    }

    return function stopResizeController() {
      if (observer) observer.disconnect();
      if (typeof global.removeEventListener === "function") {
        global.removeEventListener("resize", onWindowResize);
      }
    };
  }

  function configureCanvasElement(canvas) {
    canvas.style.display = "block";
    if (!canvas.style.width) canvas.style.width = "100%";
    if (!canvas.style.height) canvas.style.height = "100%";
    canvas.style.background = BACKGROUND;
  }

  function canvasPixelSize(canvas) {
    const rect = canvas.getBoundingClientRect();
    const cssWidth = Math.max(
      1,
      rect.width || canvas.clientWidth || canvas.width || 1,
    );
    const cssHeight = Math.max(
      1,
      rect.height || canvas.clientHeight || canvas.height || 1,
    );
    const dpr = Math.min(2, Math.max(1, global.devicePixelRatio || 1));
    return {
      width: Math.max(1, Math.round(cssWidth * dpr)),
      height: Math.max(1, Math.round(cssHeight * dpr)),
      cssWidth,
      cssHeight,
      dpr,
    };
  }

  function makeVertexSource(webgl2) {
    if (webgl2) {
      return `#version 300 es
in vec2 aPosition;
out vec2 vUv;
void main() {
  vUv = aPosition * 0.5 + 0.5;
  gl_Position = vec4(aPosition, 0.0, 1.0);
}`;
    }
    return `attribute vec2 aPosition;
varying vec2 vUv;
void main() {
  vUv = aPosition * 0.5 + 0.5;
  gl_Position = vec4(aPosition, 0.0, 1.0);
}`;
  }

  function makeFragmentSource(genome, webgl2, precision) {
    const version = webgl2 ? "#version 300 es\n" : "";
    const varying = webgl2 ? "in vec2 vUv;" : "varying vec2 vUv;";
    const outputDeclaration = webgl2 ? "out vec4 fragColor;" : "";
    const outputName = webgl2 ? "fragColor" : "gl_FragColor";

    const constants = GENOME_KEYS.map(
      (key) =>
        `const float G_${key.toUpperCase()} = ${formatFloat(genome[key])};`,
    ).join("\n");
    const lostLawExpression = GENOME_KEYS.map(
      (key) => `(1.0 - step(0.0005, ${key}))`,
    ).join(" +\n    ");

    return `${version}precision ${precision} float;

${varying}
${outputDeclaration}

uniform vec2 uResolution;
uniform float uTime;
uniform vec2 uPointer;
uniform float uPreviewMix;
uniform float uImpact;
uniform float uGravity;
uniform float uMemory;
uniform float uAttraction;
uniform float uTurbulence;
uniform float uTempo;
uniform float uLight;
uniform float uSpectrum;
uniform float uSymmetry;
uniform float uCohesion;
uniform float uDrift;
uniform float uFracture;
uniform float uTouch;
uniform float uSound;
uniform float uDepth;
uniform float uScale;
uniform float uElasticity;
uniform float uDecay;
uniform float uContinuity;
uniform float uTemperature;
uniform float uAgency;

${constants}

float hash21(vec2 p) {
  p = fract(p * vec2(123.34, 456.21));
  p += dot(p, p + 45.32);
  return fract(p.x * p.y);
}

vec2 hash22(vec2 p) {
  float n = hash21(p);
  return vec2(n, hash21(p + n + 19.19));
}

float noise2(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  f = f * f * (3.0 - 2.0 * f);
  float a = hash21(i);
  float b = hash21(i + vec2(1.0, 0.0));
  float c = hash21(i + vec2(0.0, 1.0));
  float d = hash21(i + vec2(1.0, 1.0));
  return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
}

float fbm(vec2 p) {
  float value = 0.0;
  float amplitude = 0.5;
  mat2 turn = mat2(0.82, -0.57, 0.57, 0.82);
  for (int i = 0; i < 5; i++) {
    value += amplitude * noise2(p);
    p = turn * p * 2.03 + vec2(7.1, 3.7);
    amplitude *= 0.5;
  }
  return value;
}

float angularDistance(float a, float b) {
  return abs(atan(sin(a - b), cos(a - b)));
}

void main() {
  float gravity = mix(G_GRAVITY, uGravity, uPreviewMix);
  float memory = mix(G_MEMORY, uMemory, uPreviewMix);
  float attraction = mix(G_ATTRACTION, uAttraction, uPreviewMix);
  float turbulence = mix(G_TURBULENCE, uTurbulence, uPreviewMix);
  float tempo = mix(G_TEMPO, uTempo, uPreviewMix);
  float light = mix(G_LIGHT, uLight, uPreviewMix);
  float spectrum = mix(G_SPECTRUM, uSpectrum, uPreviewMix);
  float symmetry = mix(G_SYMMETRY, uSymmetry, uPreviewMix);
  float cohesion = mix(G_COHESION, uCohesion, uPreviewMix);
  float drift = mix(G_DRIFT, uDrift, uPreviewMix);
  float fracture = mix(G_FRACTURE, uFracture, uPreviewMix);
  float touch = mix(G_TOUCH, uTouch, uPreviewMix);
  float sound = mix(G_SOUND, uSound, uPreviewMix);
  float depth = mix(G_DEPTH, uDepth, uPreviewMix);
  float scale = mix(G_SCALE, uScale, uPreviewMix);
  float elasticity = mix(G_ELASTICITY, uElasticity, uPreviewMix);
  float decay = mix(G_DECAY, uDecay, uPreviewMix);
  float continuity = mix(G_CONTINUITY, uContinuity, uPreviewMix);
  float temperature = mix(G_TEMPERATURE, uTemperature, uPreviewMix);
  float agency = mix(G_AGENCY, uAgency, uPreviewMix);
  float impact = uImpact;
  float impactProgress = 1.0 - impact;
  float lostLawCount =
    ${lostLawExpression};
  float cumulativeDamage = 1.0 - exp(-lostLawCount * 0.28);

  vec2 uv = vUv;
  float aspect = uResolution.x / max(1.0, uResolution.y);
  vec2 p = uv * 2.0 - 1.0;
  p.x *= aspect;

  float rawTime = uTime * tempo * 1.15;
  float steppedTime = floor(rawTime * 1.7) / 1.7;
  float t = mix(steppedTime, rawTime, smoothstep(0.08, 0.86, continuity));
  float continuityBreak = 1.0 - continuity;
  float slice = floor((p.y + 1.15) * 8.0);
  p.x += (hash21(vec2(slice, 17.3)) - 0.5) *
    continuityBreak * 0.16;

  vec2 autonomousDrift = vec2(
    sin(t * 0.73 + sin(t * 0.17) * 1.7),
    cos(t * 0.53 + sin(t * 0.29))
  ) * agency * 0.072;
  vec2 impactKick = vec2(
    -0.12 * impact,
    sin(impactProgress * 9.42478) * 0.055 * impact
  );
  vec2 center =
    vec2(-0.30 * aspect, 0.025) + autonomousDrift + impactKick;
  vec2 pointer = uPointer * 2.0 - 1.0;
  pointer.x *= aspect;
  float pointerField = exp(-dot(p - pointer, p - pointer) * 5.5) * touch;

  vec2 q = p - center;
  q += normalize(q + vec2(0.0001)) * pointerField *
    mix(0.025, 0.095, elasticity);
  q.x += drift * 0.075 * sin(t * 0.37 + q.y * 2.0);
  q.y += gravity * 0.026 * smoothstep(-0.2, 0.65, q.y);

  float angle = atan(q.y, q.x);
  float turbulenceNoise = fbm(
    q * mix(2.15, 4.75, turbulence) +
    vec2(t * 0.12 * drift, -t * 0.055 * (1.0 - gravity))
  );
  float mirroredNoise = fbm(
    vec2(abs(q.x), q.y) * mix(2.15, 4.75, turbulence) +
    vec2(0.0, -t * 0.04)
  );
  float organismNoise = mix(turbulenceNoise, mirroredNoise, symmetry * 0.78);

  float separation = (1.0 - attraction) * 0.12;
  vec2 separatedQ = q;
  separatedQ.x += sign(q.x + 0.0001) * separation *
    (0.35 + 0.65 * smoothstep(-0.15, 0.55, q.y));
  separatedQ.y += sign(q.y + 0.0001) * separation * 0.22;

  float radius = length(separatedQ);
  float breath = sin(t * 1.7 + organismNoise * 1.2) *
    mix(0.003, 0.028, tempo) * (0.65 + 0.35 * cohesion) * elasticity;
  float lobe = sin(angle * mix(2.0, 5.0, symmetry) + t * 0.16) *
    mix(0.07, 0.016, symmetry) * mix(0.18, 1.0, elasticity);
  float rigidFacet = pow(abs(cos(angle * 3.0)), 12.0) *
    (1.0 - elasticity) * 0.052;
  float worldScale = mix(0.08, 2.15, scale);
  float membraneRadius =
    (0.47 + breath + lobe + rigidFacet + (organismNoise - 0.5) *
    mix(0.19, 0.065, cohesion)) * worldScale;
  float sdf = radius - membraneRadius;

  float fractureAngle = mix(-0.72, 0.34, drift);
  float fracturePermission = smoothstep(0.001, 0.12, fracture);
  float impactFracture = max(
    max(fracture * 0.60, cumulativeDamage * 0.76),
    impact * 0.94
  ) * fracturePermission;
  float fractureWidth =
    0.018 +
    fracture * 0.035 +
    cumulativeDamage * 0.21 +
    impact * 0.31;
  float fractureDistance = angularDistance(angle, fractureAngle);
  float missingStrength = max(
    smoothstep(0.0, 0.22, cumulativeDamage) * 0.90,
    impact * 0.94
  ) * fracturePermission;
  float missingWedge =
    (1.0 - smoothstep(fractureWidth, fractureWidth + 0.055, fractureDistance)) *
    smoothstep(0.12, 0.31, radius) * missingStrength;
  float fractureRim =
    exp(-abs(fractureDistance - fractureWidth) * 62.0) *
    smoothstep(0.18, 0.32, radius) *
    (1.0 - smoothstep(0.50, 0.71, radius)) * impactFracture;

  float body = 1.0 - smoothstep(-0.015, 0.035, sdf);
  float erosion = smoothstep(
    mix(0.66, 0.31, cohesion),
    mix(0.83, 0.57, cohesion),
    fbm(q * 8.0 + vec2(t * 0.035, 0.0))
  );
  body *= mix(erosion, 1.0, cohesion);
  body *= 1.0 - missingWedge;
  float continuitySeams = pow(
    0.5 + 0.5 * sin((q.y + hash21(vec2(slice, 5.7)) * 0.05) * 61.0),
    28.0
  ) * continuityBreak;
  float impactSeams = pow(
    0.5 + 0.5 * sin(q.y * 83.0 + q.x * 7.0),
    30.0
  ) * impact * fracturePermission;
  continuitySeams = max(continuitySeams, impactSeams);
  body *= 1.0 - continuitySeams * 0.82;

  float membraneEdge = exp(-abs(sdf) * mix(42.0, 86.0, cohesion));
  membraneEdge *= 1.0 - missingWedge;
  float membraneTexture = smoothstep(
    0.38,
    0.72,
    fbm(q * 16.0 + vec2(t * 0.018, -t * 0.026))
  );
  membraneEdge *= 0.38 + membraneTexture * 0.62;
  membraneEdge *= 1.0 - continuitySeams * 0.55;

  float rearSdf = length(
    separatedQ + vec2(0.075, -0.055) * depth
  ) - membraneRadius * (1.0 + depth * 0.08);
  float depthLayer = exp(-abs(rearSdf) * 27.0) * depth *
    (1.0 - body) * (1.0 - missingWedge);

  float flowWarp =
    sin(q.y * 4.1 + organismNoise * 3.2 + t * 0.12) * 0.18;
  float foldPhase =
    (q.x + flowWarp) * mix(19.0, 43.0, memory) +
    q.y * mix(7.0, 18.0, symmetry) +
    angle * mix(1.2, 3.8, symmetry) +
    organismNoise * mix(8.0, 20.0, turbulence) -
    t * mix(0.12, 0.52, tempo);
  float folds = pow(0.5 + 0.5 * sin(foldPhase), 24.0) * body;
  float crossFolds = pow(
    0.5 + 0.5 * sin(q.y * 44.0 + organismNoise * 9.0 + t * 0.18),
    30.0
  ) * body * (0.25 + memory * 0.58);
  float memoryBreakup = smoothstep(
    mix(0.55, 0.16, memory),
    mix(0.78, 0.44, memory),
    noise2(q * 11.0 + floor(t * mix(1.1, 0.08, memory)))
  );
  folds *= mix(memoryBreakup, 1.0, memory);

  float persistentScars = pow(
    0.5 + 0.5 * sin(
      q.x * 37.0 - q.y * 19.0 +
      fbm(q * 5.0) * 11.0
    ),
    24.0
  ) * body * pow(1.0 - decay, 4.0);

  vec2 particleUv =
    q * vec2(94.0, 79.0) +
    vec2(t * drift * 0.32, -t * gravity * 0.09);
  vec2 particleCell = floor(particleUv);
  vec2 particlePoint = hash22(particleCell + vec2(31.7, 9.2));
  vec2 particleDelta = fract(particleUv) - particlePoint;
  float particleDensity = mix(0.30, 0.70, cumulativeDamage);
  float particleGate = 1.0 - step(
    particleDensity,
    hash21(particleCell + vec2(73.1, 18.4))
  );
  float particleSpark =
    exp(-dot(particleDelta, particleDelta) * 108.0) *
    particleGate;
  float fineBodyParticles = particleSpark * body;
  float membraneParticles =
    particleSpark * exp(-abs(sdf) * 34.0);

  vec2 cloudUv =
    q * vec2(57.0, 49.0) +
    vec2(-t * drift * 0.16, t * (1.0 - gravity) * 0.08);
  vec2 cloudCell = floor(cloudUv);
  vec2 cloudPoint = hash22(cloudCell + vec2(8.4, 61.9));
  vec2 cloudDelta = fract(cloudUv) - cloudPoint;
  float cloudDensity = mix(0.22, 0.54, cumulativeDamage);
  float cloudGate = 1.0 - step(
    cloudDensity,
    hash21(cloudCell + vec2(42.8, 3.6))
  );
  float livingCloudParticles =
    exp(-dot(cloudDelta, cloudDelta) * 82.0) *
    cloudGate *
    exp(-abs(sdf) * mix(9.0, 5.5, cumulativeDamage)) *
    (1.0 - missingWedge * 0.82);

  vec2 woundDirection = vec2(cos(fractureAngle), sin(fractureAngle));
  vec2 woundNormal = vec2(-woundDirection.y, woundDirection.x);
  float woundAlong =
    dot(q, woundDirection) - 0.37 * worldScale;
  float woundAcross = dot(q, woundNormal);
  float woundEnvelope =
    smoothstep(-0.025, 0.035, woundAlong) *
    (1.0 - smoothstep(0.05, 0.58, woundAlong)) *
    exp(-abs(woundAcross) * mix(95.0, 34.0, cumulativeDamage));
  float woundFilaments = pow(
    0.5 + 0.5 * sin(
      woundAlong * 94.0 +
      woundAcross * 41.0 +
      fbm(q * 13.0) * 7.0
    ),
    18.0
  ) * woundEnvelope * cumulativeDamage;

  float woundDebris = 0.0;
  for (int i = 0; i < 13; i++) {
    float fi = float(i);
    vec2 seed = hash22(vec2(fi * 5.83, fi * 14.17));
    float plumeDistance =
      0.40 * worldScale +
      seed.x * mix(0.08, 0.46, cumulativeDamage);
    vec2 plumePiece =
      woundDirection * plumeDistance +
      woundNormal * (seed.y - 0.5) *
        mix(0.035, 0.17, cumulativeDamage);
    float plumePointDistance = length(q - plumePiece);
    woundDebris += exp(
      -plumePointDistance * mix(138.0, 83.0, seed.x)
    );
  }
  woundDebris *= cumulativeDamage;

  float outside = smoothstep(0.0, 0.13, sdf) *
    (1.0 - smoothstep(0.15, 0.92, sdf));
  float bandPhase =
    (sdf + organismNoise * 0.035) * mix(36.0, 80.0, memory) -
    t * mix(1.05, 0.10, memory);
  float bands = pow(0.5 + 0.5 * sin(bandPhase), 19.0) * outside;
  bands *= mix(
    smoothstep(0.48, 0.78, noise2(q * 6.0 + t * 0.23)),
    1.0,
    memory
  );
  float bandFragments = smoothstep(
    0.57,
    0.76,
    fbm(q * 8.5 + vec2(t * 0.035, -t * 0.018))
  );
  bandFragments *= smoothstep(
    0.44,
    0.72,
    noise2(q * 19.0 + vec2(-t * 0.03, t * 0.022))
  );
  bands *= bandFragments;

  float soundWave = pow(
    0.5 + 0.5 * sin(
      (radius - membraneRadius) * 88.0 -
      t * 3.4 +
      angle * 2.0
    ),
    24.0
  );
  soundWave *= smoothstep(0.01, 0.08, sdf) *
    (1.0 - smoothstep(0.09, 0.62, sdf)) * sound;
  soundWave *= 0.12 + 0.88 * smoothstep(
    0.49,
    0.74,
    noise2(q * 12.0 + vec2(t * 0.04, -t * 0.025))
  );

  float streamDirection = mix(1.0, -0.12, gravity);
  vec2 flowP = p;
  flowP.y += t * 0.045 * streamDirection;
  flowP.x -= t * 0.05 * drift;
  float fieldWarp = fbm(flowP * 1.7 + organismNoise * 0.2);
  float fieldLines = pow(
    0.5 + 0.5 * sin(
      flowP.y * 15.0 +
      flowP.x * mix(1.2, 5.5, turbulence) +
      fieldWarp * 9.0
    ),
    28.0
  );
  fieldLines *= exp(-abs(p.x - center.x) * 0.58) * 0.34;
  fieldLines *= mix(0.32, 1.0, memory);
  fieldLines *= mix(0.22, 1.0, continuity);

  float debris = 0.0;
  float debrisGlow = 0.0;
  for (int i = 0; i < 12; i++) {
    float fi = float(i);
    vec2 seed = hash22(vec2(fi * 13.17, fi * 7.93));
    float orbit = 0.53 + seed.x * mix(0.22, 0.64, 1.0 - attraction);
    float theta =
      seed.y * 6.2831853 +
      t * mix(-0.035, 0.085, seed.x) * (0.4 + tempo);
    vec2 piece = center + vec2(cos(theta), sin(theta)) * orbit;
    piece.x += drift * t * 0.032 * (0.25 + seed.y);
    piece.y += streamDirection * t * 0.016 * (0.35 + seed.x);
    piece += (seed - 0.5) * separation * 2.8;
    float d = length(p - piece);
    debris += exp(-d * mix(155.0, 82.0, 1.0 - cohesion));
    debrisGlow += exp(-d * 25.0) * 0.08;
  }

  float impactDebris = 0.0;
  for (int i = 0; i < 14; i++) {
    float fi = float(i);
    vec2 seed = hash22(vec2(fi * 9.41, fi * 17.73));
    float theta = seed.x * 6.2831853 + fractureAngle * 0.35;
    float launch =
      membraneRadius * 0.72 +
      impactProgress * mix(0.34, 1.18, seed.y);
    vec2 shard = center + vec2(cos(theta), sin(theta)) * launch;
    shard += vec2(-0.22, 0.07) * impactProgress * (seed - 0.35);
    float shardDistance = length(p - shard);
    impactDebris += exp(-shardDistance * mix(120.0, 67.0, seed.y));
  }
  impactDebris *= impact;

  vec2 willOffset = vec2(
    sin(t * 1.37 + organismNoise * 2.0),
    cos(t * 1.11 - organismNoise)
  ) * 0.105 * agency * worldScale;
  float willCore = exp(-length(q - willOffset) *
    mix(88.0, 47.0, agency)) * agency;
  float willIris = exp(-abs(
    length(q - willOffset) - 0.072 * worldScale
  ) * 76.0) * agency;
  float willAura = exp(-length(q - willOffset) * 7.0) *
    agency * body;
  float decisionForks = pow(
    0.5 + 0.5 * cos(angle * 7.0 +
      sin(radius * 31.0 - t * 1.8) * 1.5),
    32.0
  );
  decisionForks *= smoothstep(0.035, 0.16, radius) *
    (1.0 - smoothstep(0.29, 0.48, radius)) * body * agency;

  float artFade = 1.0 - smoothstep(0.38 * aspect, 0.90 * aspect, p.x);
  float vignette = 1.0 - smoothstep(0.52, 1.35, length(vec2(p.x / aspect, p.y)));
  float grain = hash21(gl_FragCoord.xy + floor(t * 12.0)) - 0.5;
  float shockRadius = mix(0.12, 1.08, impactProgress);
  float impactShock = exp(-abs(length(p - center) - shockRadius) * 42.0) *
    impact;

  vec3 bg = vec3(0.014, 0.013, 0.011);
  bg += vec3(0.006, 0.008, 0.009) * fieldWarp * artFade;
  vec3 bone = vec3(${BONE});
  vec3 ember = vec3(${EMBER});
  vec3 cool = vec3(${COOL});
  vec3 coldBone = vec3(0.46, 0.62, 0.68);
  vec3 thermalBone = mix(coldBone, bone, temperature);
  vec3 thermalEmber = mix(vec3(0.18, 0.52, 0.72), ember, temperature);
  vec3 spectral = mix(thermalBone, cool, spectrum * 0.44);

  vec3 color = bg;
  float depthShade = mix(
    1.0,
    0.48 + 0.78 * smoothstep(-0.55, 0.42, q.y),
    depth
  );
  color += cool * depthLayer * (0.12 + depth * 0.42);
  color += spectral * body * (0.035 + organismNoise * 0.075) * depthShade;
  color += spectral * membraneEdge * mix(0.26, 0.72, light);
  color += mix(thermalBone, cool, spectrum * 0.72) * folds *
    mix(0.055, 0.22, light);
  color += thermalBone * crossFolds * 0.045;
  color += mix(
    thermalBone,
    thermalEmber,
    cumulativeDamage * 0.38
  ) * fineBodyParticles * mix(0.68, 1.08, cumulativeDamage);
  color += thermalBone * membraneParticles *
    mix(0.42, 0.80, cumulativeDamage);
  color += mix(thermalBone, cool, spectrum * 0.38) *
    livingCloudParticles * mix(0.46, 0.86, cumulativeDamage);
  color += mix(thermalBone, cool, spectrum) * bands *
    mix(0.015, 0.075, memory) * artFade;
  color += thermalBone * soundWave * mix(0.02, 0.08, sound) * artFade;
  color += cool * fieldLines * spectrum * artFade;
  color += mix(thermalBone, cool, spectrum * 0.65) * debris *
    0.82 * artFade;
  color += cool * debrisGlow * spectrum * artFade;
  color += thermalEmber * persistentScars * 0.48;
  color += thermalEmber * woundFilaments * 0.86;
  color += mix(thermalEmber, thermalBone, 0.32) *
    woundDebris * 1.10;
  color += thermalEmber * fractureRim *
    mix(0.45, 1.18, impactFracture) * artFade;
  color += thermalEmber * impactShock * 1.34;
  color += mix(thermalEmber, thermalBone, 0.42) *
    impactDebris * 1.15;
  color += thermalEmber * pointerField * membraneEdge * 0.62;
  color += thermalEmber * willAura * 0.12;
  color += thermalEmber * willIris * 0.72;
  color += thermalEmber * willCore * 1.48;
  color += mix(thermalEmber, thermalBone, 0.58) * decisionForks * 0.62;
  color *= mix(0.10, 1.36, light);
  color *= 0.62 + 0.38 * vignette;
  color += grain * 0.009;

  ${outputName} = vec4(max(color, vec3(0.0)), 1.0);
}`;
  }

  function shaderPrecision(gl, webgl2) {
    if (webgl2) return "highp";
    try {
      const info = gl.getShaderPrecisionFormat(
        gl.FRAGMENT_SHADER,
        gl.HIGH_FLOAT,
      );
      return info && info.precision > 0 ? "highp" : "mediump";
    } catch (_error) {
      return "mediump";
    }
  }

  function compileShader(gl, type, source) {
    const shader = gl.createShader(type);
    if (!shader) return { shader: null, error: "Unable to allocate shader." };
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      const error = gl.getShaderInfoLog(shader) || "Unknown shader error.";
      gl.deleteShader(shader);
      return { shader: null, error };
    }
    return { shader, error: null };
  }

  function compileProgram(gl, vertexShader, fragmentSource) {
    const start = nowMs();
    const fragmentResult = compileShader(
      gl,
      gl.FRAGMENT_SHADER,
      fragmentSource,
    );
    if (!fragmentResult.shader) {
      return {
        ok: false,
        ms: nowMs() - start,
        error: fragmentResult.error,
        program: null,
      };
    }

    const program = gl.createProgram();
    if (!program) {
      gl.deleteShader(fragmentResult.shader);
      return {
        ok: false,
        ms: nowMs() - start,
        error: "Unable to allocate WebGL program.",
        program: null,
      };
    }

    gl.attachShader(program, vertexShader);
    gl.attachShader(program, fragmentResult.shader);
    gl.linkProgram(program);
    const ok = Boolean(gl.getProgramParameter(program, gl.LINK_STATUS));
    const error = ok ? null : gl.getProgramInfoLog(program) || "Link failed.";
    gl.detachShader(program, fragmentResult.shader);
    gl.deleteShader(fragmentResult.shader);

    if (!ok) {
      gl.deleteProgram(program);
      return { ok: false, ms: nowMs() - start, error, program: null };
    }

    return { ok: true, ms: nowMs() - start, error: null, program };
  }

  function createWebGLWorld(canvas, gl, webgl2, options) {
    const onCompile = options && options.onCompile;
    const precision = shaderPrecision(gl, webgl2);
    const vertexSource = makeVertexSource(webgl2);
    const vertexResult = compileShader(gl, gl.VERTEX_SHADER, vertexSource);
    let destroyed = false;
    let animationFrame = 0;
    let currentProgram = null;
    let currentLocations = null;
    let committedGenome = copyGenome(DEFAULT_GENOME);
    let previewGenome = null;
    let hasCommittedProgram = false;
    let hasAppliedWorldState = false;
    let impactStartedAt = Number.NEGATIVE_INFINITY;
    let width = 1;
    let height = 1;
    let startTime = nowMs();
    let lastDrawTime = 0;
    let pointer = [-4, -4];
    let pointerTarget = [-4, -4];
    let reducedMotion = false;
    const media = motionQuery();

    const vertexBuffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, vertexBuffer);
    gl.bufferData(
      gl.ARRAY_BUFFER,
      new Float32Array([-1, -1, 3, -1, -1, 3]),
      gl.STATIC_DRAW,
    );

    function resize() {
      if (destroyed) return;
      const size = canvasPixelSize(canvas);
      if (canvas.width !== size.width || canvas.height !== size.height) {
        canvas.width = size.width;
        canvas.height = size.height;
      }
      width = size.width;
      height = size.height;
      gl.viewport(0, 0, width, height);
    }

    const stopResize = createResizeController(canvas, resize);

    function updateMotionPreference() {
      reducedMotion = Boolean(media && media.matches);
    }
    updateMotionPreference();
    if (media) {
      if (typeof media.addEventListener === "function") {
        media.addEventListener("change", updateMotionPreference);
      } else if (typeof media.addListener === "function") {
        media.addListener(updateMotionPreference);
      }
    }

    function locateProgram(program) {
      const uniforms = {};
      [
        "uResolution",
        "uTime",
        "uPointer",
        "uPreviewMix",
        "uImpact",
        "uGravity",
        "uMemory",
        "uAttraction",
        "uTurbulence",
        "uTempo",
        "uLight",
        "uSpectrum",
        "uSymmetry",
        "uCohesion",
        "uDrift",
        "uFracture",
        "uTouch",
        "uSound",
        "uDepth",
        "uScale",
        "uElasticity",
        "uDecay",
        "uContinuity",
        "uTemperature",
        "uAgency",
      ].forEach((name) => {
        uniforms[name] = gl.getUniformLocation(program, name);
      });
      return {
        position: gl.getAttribLocation(program, "aPosition"),
        uniforms,
      };
    }

    function compileAndCommit(nextGenome, allowImpact) {
      const previous = hasCommittedProgram ? committedGenome : null;
      const changed = genomesDiffer(previous, nextGenome);
      const diffLines = genomeDiff(previous, nextGenome);
      const source = makeFragmentSource(nextGenome, webgl2, precision);

      if (!vertexResult.shader) {
        const payload = {
          ok: false,
          success: false,
          ms: 0,
          measuredMs: 0,
          source,
          sourceLines: source.split("\n"),
          diffLines,
          genome: copyGenome(nextGenome),
          error: vertexResult.error,
        };
        safeNotify(onCompile, payload);
        return payload;
      }

      const result = compileProgram(gl, vertexResult.shader, source);
      const payload = {
        ok: result.ok,
        success: result.ok,
        ms: result.ms,
        measuredMs: result.ms,
        source,
        sourceLines: source.split("\n"),
        diffLines,
        genome: copyGenome(nextGenome),
        error: result.error,
      };

      if (result.ok) {
        const previousProgram = currentProgram;
        currentProgram = result.program;
        currentLocations = locateProgram(currentProgram);
        committedGenome = copyGenome(nextGenome);
        previewGenome = null;
        hasCommittedProgram = true;
        if (allowImpact && changed) impactStartedAt = nowMs();
        if (previousProgram) gl.deleteProgram(previousProgram);
      }

      safeNotify(onCompile, payload);
      return payload;
    }

    function setPreviewUniforms(genome) {
      const uniforms = currentLocations.uniforms;
      gl.uniform1f(uniforms.uGravity, genome.gravity);
      gl.uniform1f(uniforms.uMemory, genome.memory);
      gl.uniform1f(uniforms.uAttraction, genome.attraction);
      gl.uniform1f(uniforms.uTurbulence, genome.turbulence);
      gl.uniform1f(uniforms.uTempo, genome.tempo);
      gl.uniform1f(uniforms.uLight, genome.light);
      gl.uniform1f(uniforms.uSpectrum, genome.spectrum);
      gl.uniform1f(uniforms.uSymmetry, genome.symmetry);
      gl.uniform1f(uniforms.uCohesion, genome.cohesion);
      gl.uniform1f(uniforms.uDrift, genome.drift);
      gl.uniform1f(uniforms.uFracture, genome.fracture);
      gl.uniform1f(uniforms.uTouch, genome.touch);
      gl.uniform1f(uniforms.uSound, genome.sound);
      gl.uniform1f(uniforms.uDepth, genome.depth);
      gl.uniform1f(uniforms.uScale, genome.scale);
      gl.uniform1f(uniforms.uElasticity, genome.elasticity);
      gl.uniform1f(uniforms.uDecay, genome.decay);
      gl.uniform1f(uniforms.uContinuity, genome.continuity);
      gl.uniform1f(uniforms.uTemperature, genome.temperature);
      gl.uniform1f(uniforms.uAgency, genome.agency);
    }

    function draw(timestamp, force) {
      if (destroyed || !currentProgram || !currentLocations) return;
      resize();

      if (
        reducedMotion &&
        !force &&
        lastDrawTime &&
        timestamp - lastDrawTime < 240
      ) {
        return;
      }
      lastDrawTime = timestamp;

      pointer[0] += (pointerTarget[0] - pointer[0]) * 0.11;
      pointer[1] += (pointerTarget[1] - pointer[1]) * 0.11;

      gl.useProgram(currentProgram);
      gl.bindBuffer(gl.ARRAY_BUFFER, vertexBuffer);
      gl.enableVertexAttribArray(currentLocations.position);
      gl.vertexAttribPointer(
        currentLocations.position,
        2,
        gl.FLOAT,
        false,
        0,
        0,
      );

      const uniforms = currentLocations.uniforms;
      const elapsed = Math.max(0, (timestamp - startTime) / 1000);
      const visualTime = reducedMotion ? elapsed * 0.045 : elapsed;
      const impactAge = Math.max(0, timestamp - impactStartedAt);
      const impact =
        !reducedMotion && impactAge < 1100
          ? Math.pow(1 - impactAge / 1100, 0.72)
          : 0;
      gl.uniform2f(uniforms.uResolution, width, height);
      gl.uniform1f(uniforms.uTime, visualTime);
      gl.uniform2f(uniforms.uPointer, pointer[0], pointer[1]);
      gl.uniform1f(uniforms.uPreviewMix, previewGenome ? 1 : 0);
      gl.uniform1f(uniforms.uImpact, impact);
      setPreviewUniforms(previewGenome || committedGenome);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    }

    function loop(timestamp) {
      if (destroyed) return;
      draw(timestamp, false);
      animationFrame = global.requestAnimationFrame(loop);
    }

    function drawNow() {
      draw(nowMs(), true);
    }

    function apply(worldState) {
      if (destroyed) return null;
      const nextGenome = normalizeGenome(worldState, committedGenome);
      const result = compileAndCommit(nextGenome, hasAppliedWorldState);
      if (result && result.ok) hasAppliedWorldState = true;
      drawNow();
      return result;
    }

    function preview(option) {
      if (destroyed || !currentProgram) return null;
      previewGenome = normalizeGenome(option, committedGenome);
      drawNow();
      return copyGenome(previewGenome);
    }

    function clearPreview() {
      if (destroyed) return;
      previewGenome = null;
      drawNow();
    }

    function setPointer(x, y) {
      if (destroyed) return;
      if (!Number.isFinite(Number(x)) || !Number.isFinite(Number(y))) {
        pointerTarget = [-4, -4];
        return;
      }

      let nx = Number(x);
      let ny = Number(y);
      if (
        (nx < 0 || ny < 0) &&
        nx >= -1 &&
        nx <= 1 &&
        ny >= -1 &&
        ny <= 1
      ) {
        nx = nx * 0.5 + 0.5;
        ny = 1 - (ny * 0.5 + 0.5);
      } else if (nx < 0 || nx > 1 || ny < 0 || ny > 1) {
        const rect = canvas.getBoundingClientRect();
        nx = rect.width ? (nx - rect.left) / rect.width : 0.5;
        ny = rect.height ? (ny - rect.top) / rect.height : 0.5;
      }
      pointerTarget = [clamp01(nx), 1 - clamp01(ny)];
      if (reducedMotion) drawNow();
    }

    function onPointerMove(event) {
      setPointer(event.clientX, event.clientY);
    }
    function onPointerLeave() {
      pointerTarget = [-4, -4];
    }
    canvas.addEventListener("pointermove", onPointerMove, { passive: true });
    canvas.addEventListener("pointerleave", onPointerLeave, { passive: true });

    function destroy() {
      if (destroyed) return;
      destroyed = true;
      if (animationFrame) global.cancelAnimationFrame(animationFrame);
      stopResize();
      canvas.removeEventListener("pointermove", onPointerMove);
      canvas.removeEventListener("pointerleave", onPointerLeave);
      if (media) {
        if (typeof media.removeEventListener === "function") {
          media.removeEventListener("change", updateMotionPreference);
        } else if (typeof media.removeListener === "function") {
          media.removeListener(updateMotionPreference);
        }
      }
      if (currentProgram) gl.deleteProgram(currentProgram);
      if (vertexResult.shader) gl.deleteShader(vertexResult.shader);
      if (vertexBuffer) gl.deleteBuffer(vertexBuffer);
      currentProgram = null;
      currentLocations = null;
      if (activeWorld === api) activeWorld = null;
    }

    const api = {
      apply,
      preview,
      clearPreview,
      setPointer,
      destroy,
      get genome() {
        return copyGenome(committedGenome);
      },
      get isFallback() {
        return false;
      },
    };

    resize();
    compileAndCommit(DEFAULT_GENOME, false);
    drawNow();
    animationFrame = global.requestAnimationFrame(loop);
    return api;
  }

  function createFallbackWorld(canvas, options, reason) {
    const context = canvas.getContext("2d");
    const onCompile = options && options.onCompile;
    let destroyed = false;
    let animationFrame = 0;
    let committedGenome = copyGenome(DEFAULT_GENOME);
    let previewGenome = null;
    let pointer = [-4, -4];
    let reducedMotion = false;
    let lastDrawTime = 0;
    let startTime = nowMs();
    let hasAppliedWorldState = false;
    let impactStartedAt = Number.NEGATIVE_INFINITY;
    const media = motionQuery();

    function resize() {
      if (destroyed || !context) return;
      const size = canvasPixelSize(canvas);
      if (canvas.width !== size.width || canvas.height !== size.height) {
        canvas.width = size.width;
        canvas.height = size.height;
      }
    }

    const stopResize = createResizeController(canvas, resize);

    function updateMotionPreference() {
      reducedMotion = Boolean(media && media.matches);
    }
    updateMotionPreference();
    if (media) {
      if (typeof media.addEventListener === "function") {
        media.addEventListener("change", updateMotionPreference);
      } else if (typeof media.addListener === "function") {
        media.addListener(updateMotionPreference);
      }
    }

    function draw(timestamp, force) {
      if (destroyed || !context) return;
      if (
        reducedMotion &&
        !force &&
        lastDrawTime &&
        timestamp - lastDrawTime < 260
      ) {
        return;
      }
      lastDrawTime = timestamp;
      resize();

      const genome = previewGenome || committedGenome;
      const width = canvas.width;
      const height = canvas.height;
      const lostLawCount = GENOME_KEYS.reduce(
        (count, key) => count + (genome[key] <= 0.0005 ? 1 : 0),
        0,
      );
      const cumulativeDamage =
        1 - Math.exp(-lostLawCount * 0.28);
      const rawT =
        ((timestamp - startTime) / 1000) *
        (reducedMotion ? 0.035 : 1) *
        genome.tempo *
        1.15;
      const steppedT = Math.floor(rawT * 1.7) / 1.7;
      const continuityMix = Math.max(
        0,
        Math.min(1, (genome.continuity - 0.08) / 0.78),
      );
      const t = steppedT * (1 - continuityMix) + rawT * continuityMix;
      const impactAge = Math.max(0, timestamp - impactStartedAt);
      const impact =
        !reducedMotion && impactAge < 1100
          ? Math.pow(1 - impactAge / 1100, 0.72)
          : 0;
      const impactProgress = 1 - impact;
      const autonomyX =
        Math.sin(t * 0.73 + Math.sin(t * 0.17) * 1.7) *
        genome.agency *
        width *
        0.025;
      const autonomyY =
        Math.cos(t * 0.53 + Math.sin(t * 0.29)) *
        genome.agency *
        height *
        0.032;
      const cx =
        width * 0.34 + autonomyX - width * impact * 0.042;
      const cy =
        height * 0.5 +
        autonomyY +
        Math.sin(impactProgress * Math.PI * 3) *
          height *
          impact *
          0.028;
      const worldScale = 0.08 + genome.scale * 2.07;
      const baseRadius =
        Math.min(width, height) * 0.29 * worldScale;
      const coldBone = [112, 157, 174];
      const warmBone = [225, 218, 201];
      const coldEmber = [46, 133, 184];
      const warmEmber = [255, 73, 30];
      const mixRgb = (cold, warm) =>
        cold.map((value, index) =>
          Math.round(
            value + (warm[index] - value) * genome.temperature,
          ),
        );
      const boneRgb = mixRgb(coldBone, warmBone);
      const emberRgb = mixRgb(coldEmber, warmEmber);

      context.fillStyle = BACKGROUND;
      context.fillRect(0, 0, width, height);
      context.save();
      context.globalAlpha = 0.1 + genome.light * 0.9;

      const glow = context.createRadialGradient(
        cx,
        cy,
        baseRadius * 0.08,
        cx,
        cy,
        baseRadius * 1.7,
      );
      glow.addColorStop(0, "rgba(224,216,197,0.07)");
      glow.addColorStop(0.5, "rgba(82,105,110,0.025)");
      glow.addColorStop(1, "rgba(8,8,7,0)");
      context.fillStyle = glow;
      context.fillRect(0, 0, width * 0.78, height);

      const fractureAngle = -0.72 + genome.drift * 1.06;
      const fracturePermission = Math.max(
        0,
        Math.min(1, (genome.fracture - 0.001) / 0.119),
      );
      const missingRamp = Math.max(
        0,
        Math.min(1, cumulativeDamage / 0.22),
      );
      const persistentMissing =
        missingRamp * missingRamp * (3 - 2 * missingRamp) * 0.9;
      const missingStrength =
        Math.max(persistentMissing, impact * 0.94) *
        fracturePermission;
      const fractureWidth =
        0.018 +
        genome.fracture * 0.035 +
        cumulativeDamage * 0.21 +
        impact * 0.31;

      context.beginPath();
      let drawing = false;
      const points = 150;
      for (let i = 0; i <= points; i += 1) {
        const a = (i / points) * Math.PI * 2 - Math.PI;
        const angularGap = Math.abs(
          Math.atan2(
            Math.sin(a - fractureAngle),
            Math.cos(a - fractureAngle),
          ),
        );
        const missing =
          missingStrength > 0.04 &&
          angularGap < fractureWidth * 0.72;
        const continuityGap =
          (genome.continuity < 0.82 ||
            impact * fracturePermission > 0.02) &&
          i % 19 <
            Math.ceil(
              Math.max(
                1 - genome.continuity,
                impact * fracturePermission,
              ) * 3,
            );
        if (missing || continuityGap) {
          drawing = false;
          continue;
        }
        const asymmetry =
          Math.sin(a * (2 + genome.symmetry * 3) + t * 0.31) *
          (0.085 - genome.symmetry * 0.058) *
          (0.18 + genome.elasticity * 0.82);
        const turbulence =
          Math.sin(a * 7.3 + t * 0.47) *
          Math.sin(a * 3.1 - t * 0.19) *
          genome.turbulence *
          0.055 *
          (0.2 + genome.elasticity * 0.8);
        const breath =
          Math.sin(t * 1.45) *
          genome.tempo *
          genome.elasticity *
          0.025;
        const rigidFacet =
          Math.pow(Math.abs(Math.cos(a * 3)), 12) *
          (1 - genome.elasticity) *
          0.052;
        const radius =
          baseRadius *
          (1 + asymmetry + turbulence + breath + rigidFacet);
        const x = cx + Math.cos(a) * radius;
        const y = cy + Math.sin(a) * radius;
        if (!drawing) {
          context.moveTo(x, y);
          drawing = true;
        } else {
          context.lineTo(x, y);
        }
      }
      context.closePath();

      context.save();
      context.translate(
        baseRadius * genome.depth * 0.095,
        -baseRadius * genome.depth * 0.07,
      );
      context.strokeStyle = `rgba(72,119,132,${genome.depth * 0.38})`;
      context.lineWidth = Math.max(
        1,
        (canvas.width / 950) * (0.3 + genome.depth),
      );
      context.stroke();
      context.restore();

      const membrane = context.createRadialGradient(
        cx - baseRadius * 0.18,
        cy - baseRadius * 0.25,
        baseRadius * 0.08,
        cx,
        cy,
        baseRadius * 1.15,
      );
      membrane.addColorStop(
        0,
        `rgba(${boneRgb.join(",")},${0.035 + genome.depth * 0.05})`,
      );
      membrane.addColorStop(0.72, "rgba(139,148,145,0.018)");
      membrane.addColorStop(1, "rgba(8,8,7,0)");
      context.fillStyle = membrane;
      context.fill();
      context.strokeStyle = `rgba(${boneRgb.join(",")},${0.18 + genome.depth * 0.25})`;
      context.lineWidth = Math.max(0.7, canvas.width / 1500);
      context.stroke();

      context.save();
      context.clip();
      context.globalCompositeOperation = "lighter";
      const fineParticleCount =
        76 + Math.round(cumulativeDamage * 82);
      for (let particle = 0; particle < fineParticleCount; particle += 1) {
        const seedA = ((particle * 53) % 127) / 127;
        const seedB = ((particle * 89) % 131) / 131;
        const particleAngle = seedA * Math.PI * 2;
        const particleRadius =
          Math.sqrt(seedB) * baseRadius * 0.93;
        const particleX =
          cx + Math.cos(particleAngle) * particleRadius;
        const particleY =
          cy +
          Math.sin(particleAngle) *
            particleRadius *
            (0.78 + genome.cohesion * 0.16);
        context.beginPath();
        context.arc(
          particleX,
          particleY,
          Math.max(0.45, width / 2600) *
            (0.72 + seedA * 0.68),
          0,
          Math.PI * 2,
        );
        context.fillStyle = `rgba(${boneRgb.join(",")},${
          0.18 + cumulativeDamage * 0.36
        })`;
        context.fill();
      }
      context.restore();

      context.save();
      context.globalCompositeOperation = "lighter";
      const cloudParticleCount =
        58 + Math.round(cumulativeDamage * 72);
      for (let particle = 0; particle < cloudParticleCount; particle += 1) {
        const seedA = ((particle * 67) % 149) / 149;
        const seedB = ((particle * 97) % 157) / 157;
        const cloudAngle =
          seedA * Math.PI * 2 +
          Math.sin(seedB * 19.0) * 0.13;
        const cloudRadius =
          baseRadius *
          (0.78 +
            seedB *
              (0.52 + cumulativeDamage * 0.58));
        const cloudX =
          cx +
          Math.cos(cloudAngle) *
            cloudRadius *
            (1 + genome.turbulence * 0.08);
        const cloudY =
          cy +
          Math.sin(cloudAngle) *
            cloudRadius *
            (0.77 + genome.cohesion * 0.16);
        context.beginPath();
        context.arc(
          cloudX,
          cloudY,
          Math.max(0.5, width / 2500) * (0.7 + seedB),
          0,
          Math.PI * 2,
        );
        context.fillStyle = `rgba(${boneRgb.join(",")},${
          0.08 + cumulativeDamage * 0.20
        })`;
        context.fill();
      }
      context.restore();

      if (impact > 0.001) {
        const shockRadius =
          baseRadius * 0.4 +
          Math.min(width, height) * 0.51 * impactProgress;
        context.beginPath();
        context.arc(cx, cy, shockRadius, 0, Math.PI * 2);
        context.strokeStyle = `rgba(${emberRgb.join(",")},${
          impact * 0.88
        })`;
        context.lineWidth = Math.max(
          1,
          width / 560 * (0.45 + impact),
        );
        context.stroke();
      }

      context.save();
      context.globalCompositeOperation = "lighter";
      if (cumulativeDamage > 0.001) {
        const woundDirection = [
          Math.cos(fractureAngle),
          Math.sin(fractureAngle),
        ];
        const woundNormal = [-woundDirection[1], woundDirection[0]];
        const woundOrigin = [
          cx + woundDirection[0] * baseRadius * 0.78,
          cy + woundDirection[1] * baseRadius * 0.78,
        ];
        for (let filament = 0; filament < 9; filament += 1) {
          const offset = (filament / 8 - 0.5) *
            baseRadius * 0.15 * cumulativeDamage;
          const length =
            baseRadius *
            (0.12 + cumulativeDamage * (0.24 + filament * 0.018));
          context.beginPath();
          context.moveTo(
            woundOrigin[0] + woundNormal[0] * offset,
            woundOrigin[1] + woundNormal[1] * offset,
          );
          context.quadraticCurveTo(
            woundOrigin[0] +
              woundDirection[0] * length * 0.48 +
              woundNormal[0] * offset * 1.8,
            woundOrigin[1] +
              woundDirection[1] * length * 0.48 +
              woundNormal[1] * offset * 1.8,
            woundOrigin[0] +
              woundDirection[0] * length +
              woundNormal[0] * offset * 2.3,
            woundOrigin[1] +
              woundDirection[1] * length +
              woundNormal[1] * offset * 2.3,
          );
          context.strokeStyle = `rgba(${emberRgb.join(",")},${
            cumulativeDamage *
            (0.12 + fracturePermission * 0.13)
          })`;
          context.lineWidth = Math.max(0.45, width / 2800);
          context.stroke();
        }
        for (let mote = 0; mote < 18; mote += 1) {
          const seed = ((mote * 37) % 101) / 101;
          const distance =
            baseRadius *
            (0.08 + seed * 0.38) *
            cumulativeDamage;
          const spread =
            (seed - 0.5) *
            baseRadius *
            0.18 *
            cumulativeDamage;
          context.beginPath();
          context.arc(
            woundOrigin[0] +
              woundDirection[0] * distance +
              woundNormal[0] * spread,
            woundOrigin[1] +
              woundDirection[1] * distance +
              woundNormal[1] * spread,
            Math.max(0.55, width / 2350) * (0.7 + seed),
            0,
            Math.PI * 2,
          );
          context.fillStyle = `rgba(${emberRgb.join(",")},${
            cumulativeDamage * (0.18 + seed * 0.22)
          })`;
          context.fill();
        }
      }
      for (let band = 0; band < 8; band += 1) {
        const phase = band / 8;
        context.beginPath();
        const radius =
          baseRadius *
          (0.23 + phase * 0.74) *
          (1 + Math.sin(t * 0.15 + band) * 0.008);
        context.ellipse(
          cx,
          cy,
          radius * (1 + (1 - genome.symmetry) * 0.08),
          radius * (0.76 + genome.cohesion * 0.19),
          genome.drift * 0.3 + phase * 0.07,
          0,
          Math.PI * 2,
        );
        const alpha =
          (0.004 + genome.memory * 0.009) *
          (0.35 + genome.depth * 0.65);
        context.strokeStyle =
          genome.spectrum > 0.55
            ? `rgba(92,139,151,${alpha})`
            : `rgba(${boneRgb.join(",")},${alpha})`;
        context.lineWidth = Math.max(0.5, width / 2400);
        context.stroke();
      }

      for (let ring = 0; ring < 3; ring += 1) {
        const wavePhase = (t * 0.17 + ring / 3) % 1;
        const ringRadius =
          baseRadius * (1.04 + wavePhase * 1.45);
        context.beginPath();
        context.ellipse(
          cx,
          cy,
          ringRadius,
          ringRadius * (0.82 + genome.depth * 0.14),
          0,
          0,
          Math.PI * 2,
        );
        context.strokeStyle = `rgba(${boneRgb.join(",")},${
          genome.sound * (1 - wavePhase) * 0.06
        })`;
        context.lineWidth = Math.max(0.5, width / 2600);
        context.stroke();
      }

      for (let i = 0; i < 72; i += 1) {
        const seedA = ((i * 47) % 97) / 97;
        const seedB = ((i * 71) % 101) / 101;
        const angle = seedA * Math.PI * 2 + t * (0.004 + seedB * 0.012);
        const orbit =
          baseRadius * (1.05 + seedB * (0.5 + (1 - genome.attraction)));
        const rise =
          (1 - genome.gravity) *
          ((t * (8 + seedA * 11)) % (height * 0.22));
        const x =
          cx +
          Math.cos(angle) * orbit +
          genome.drift * t * 12;
        const y = cy + Math.sin(angle) * orbit - rise;
        const distanceToPointer =
          pointer[0] < -1
            ? 99
            : Math.hypot(
                x - pointer[0] * width,
                y - (1 - pointer[1]) * height,
              );
        const pointRadius =
          Math.max(0.6, width / 1800) +
          Math.exp(-distanceToPointer / 75) * genome.touch * 1.8;
        const trailStrength = Math.pow(1 - genome.decay, 4);
        if (trailStrength > 0.01) {
          const trailLength =
            baseRadius * (0.04 + trailStrength * 0.24);
          context.beginPath();
          context.moveTo(x, y);
          context.lineTo(
            x -
              Math.cos(angle) *
                trailLength *
                (0.25 + genome.drift),
            y +
              trailLength *
                (0.22 + (1 - genome.gravity) * 0.65),
          );
          context.strokeStyle = `rgba(${boneRgb.join(",")},${
            trailStrength * 0.15
          })`;
          context.lineWidth = Math.max(0.45, width / 2700);
          context.stroke();
        }
        context.beginPath();
        context.arc(x, y, pointRadius, 0, Math.PI * 2);
        context.fillStyle =
          i % 13 === 0
            ? `rgba(${emberRgb.join(",")},${0.16 + genome.fracture * 0.34})`
            : `rgba(${boneRgb.join(",")},${0.09 + genome.depth * 0.2})`;
        context.fill();
      }

      if (impact > 0.001) {
        for (let shard = 0; shard < 14; shard += 1) {
          const seed = ((shard * 47) % 101) / 101;
          const shardAngle =
            seed * Math.PI * 2 - 0.72 + genome.drift * 1.06;
          const launch =
            baseRadius * 0.7 +
            Math.min(width, height) *
              impactProgress *
              (0.18 + seed * 0.35);
          const shardX = cx + Math.cos(shardAngle) * launch;
          const shardY = cy + Math.sin(shardAngle) * launch;
          context.beginPath();
          context.arc(
            shardX,
            shardY,
            Math.max(0.8, width / 1500) *
              (0.65 + impact),
            0,
            Math.PI * 2,
          );
          context.fillStyle = `rgba(${emberRgb.join(",")},${
            impact * (0.42 + seed * 0.46)
          })`;
          context.fill();
        }
      }

      if (genome.agency > 0.001) {
        const willX =
          cx + Math.sin(t * 1.37) * baseRadius * 0.21 * genome.agency;
        const willY =
          cy + Math.cos(t * 1.11) * baseRadius * 0.17 * genome.agency;
        for (let branch = 0; branch < 7; branch += 1) {
          const branchAngle =
            (branch / 7) * Math.PI * 2 +
            Math.sin(t * 0.43 + branch) * 0.25;
          context.beginPath();
          context.moveTo(willX, willY);
          context.quadraticCurveTo(
            cx +
              Math.cos(branchAngle + 0.34) *
                baseRadius *
                0.23,
            cy +
              Math.sin(branchAngle - 0.2) *
                baseRadius *
                0.19,
            cx +
              Math.cos(branchAngle) *
                baseRadius *
                (0.32 + genome.agency * 0.13),
            cy +
              Math.sin(branchAngle) *
                baseRadius *
                (0.32 + genome.agency * 0.13),
          );
          context.strokeStyle = `rgba(${emberRgb.join(",")},${
            genome.agency * 0.19
          })`;
          context.lineWidth = Math.max(0.55, width / 2100);
          context.stroke();
        }
        context.beginPath();
        context.arc(
          willX,
          willY,
          Math.max(2, baseRadius * 0.026 * genome.agency),
          0,
          Math.PI * 2,
        );
        context.fillStyle = `rgba(${emberRgb.join(",")},${
          0.34 + genome.agency * 0.55
        })`;
        context.fill();
      }
      context.restore();
      context.restore();
    }

    function loop(timestamp) {
      if (destroyed) return;
      draw(timestamp, false);
      animationFrame = global.requestAnimationFrame(loop);
    }

    function report(nextGenome, previousGenome) {
      const diffLines = genomeDiff(previousGenome, nextGenome);
      const payload = {
        ok: false,
        success: false,
        fallback: true,
        ms: 0,
        measuredMs: 0,
        source: "",
        sourceLines: [],
        diffLines,
        genome: copyGenome(nextGenome),
        error: reason || "WebGL unavailable; using the 2D artwork fallback.",
      };
      safeNotify(onCompile, payload);
      return payload;
    }

    function apply(worldState) {
      if (destroyed) return null;
      const previous = committedGenome;
      const nextGenome = normalizeGenome(worldState, committedGenome);
      const changed = genomesDiffer(previous, nextGenome);
      committedGenome = nextGenome;
      previewGenome = null;
      if (hasAppliedWorldState && changed) impactStartedAt = nowMs();
      hasAppliedWorldState = true;
      const payload = report(committedGenome, previous);
      draw(nowMs(), true);
      return payload;
    }

    function preview(option) {
      if (destroyed) return null;
      previewGenome = normalizeGenome(option, committedGenome);
      draw(nowMs(), true);
      return copyGenome(previewGenome);
    }

    function clearPreview() {
      if (destroyed) return;
      previewGenome = null;
      draw(nowMs(), true);
    }

    function setPointer(x, y) {
      if (!Number.isFinite(Number(x)) || !Number.isFinite(Number(y))) {
        pointer = [-4, -4];
        return;
      }
      let nx = Number(x);
      let ny = Number(y);
      if (nx < 0 || nx > 1 || ny < 0 || ny > 1) {
        const rect = canvas.getBoundingClientRect();
        nx = rect.width ? (nx - rect.left) / rect.width : 0.5;
        ny = rect.height ? (ny - rect.top) / rect.height : 0.5;
      }
      pointer = [clamp01(nx), 1 - clamp01(ny)];
      if (reducedMotion) draw(nowMs(), true);
    }

    function onPointerMove(event) {
      setPointer(event.clientX, event.clientY);
    }
    function onPointerLeave() {
      pointer = [-4, -4];
    }
    canvas.addEventListener("pointermove", onPointerMove, { passive: true });
    canvas.addEventListener("pointerleave", onPointerLeave, { passive: true });

    function destroy() {
      if (destroyed) return;
      destroyed = true;
      if (animationFrame) global.cancelAnimationFrame(animationFrame);
      stopResize();
      canvas.removeEventListener("pointermove", onPointerMove);
      canvas.removeEventListener("pointerleave", onPointerLeave);
      if (media) {
        if (typeof media.removeEventListener === "function") {
          media.removeEventListener("change", updateMotionPreference);
        } else if (typeof media.removeListener === "function") {
          media.removeListener(updateMotionPreference);
        }
      }
      if (activeWorld === api) activeWorld = null;
    }

    const api = {
      apply,
      preview,
      clearPreview,
      setPointer,
      destroy,
      get genome() {
        return copyGenome(committedGenome);
      },
      get isFallback() {
        return true;
      },
    };

    resize();
    report(committedGenome, null);
    draw(nowMs(), true);
    animationFrame = global.requestAnimationFrame(loop);
    return api;
  }

  function createNoopWorld(options, reason) {
    const onCompile = options && options.onCompile;
    const payload = {
      ok: false,
      success: false,
      fallback: true,
      ms: 0,
      measuredMs: 0,
      source: "",
      sourceLines: [],
      diffLines: [],
      genome: copyGenome(DEFAULT_GENOME),
      error: reason,
    };
    safeNotify(onCompile, payload);
    return {
      apply() {
        return payload;
      },
      preview() {
        return copyGenome(DEFAULT_GENOME);
      },
      clearPreview() {},
      setPointer() {},
      destroy() {},
      get genome() {
        return copyGenome(DEFAULT_GENOME);
      },
      get isFallback() {
        return true;
      },
    };
  }

  function mount(canvas, options) {
    if (activeWorld) activeWorld.destroy();
    if (!canvas || typeof canvas.getContext !== "function") {
      activeWorld = createNoopWorld(
        options,
        "A canvas element is required to mount the world.",
      );
      return activeWorld;
    }

    configureCanvasElement(canvas);

    let gl = null;
    let webgl2 = false;
    try {
      gl = canvas.getContext("webgl2", {
        alpha: false,
        antialias: true,
        depth: false,
        stencil: false,
        premultipliedAlpha: false,
        preserveDrawingBuffer: false,
        powerPreference: "high-performance",
      });
      webgl2 = Boolean(gl);
      if (!gl) {
        gl =
          canvas.getContext("webgl", {
            alpha: false,
            antialias: true,
            depth: false,
            stencil: false,
            premultipliedAlpha: false,
            preserveDrawingBuffer: false,
            powerPreference: "high-performance",
          }) ||
          canvas.getContext("experimental-webgl", {
            alpha: false,
            antialias: true,
            depth: false,
            stencil: false,
          });
      }
    } catch (_error) {
      gl = null;
    }

    if (gl) {
      activeWorld = createWebGLWorld(canvas, gl, webgl2, options || {});
    } else {
      activeWorld = createFallbackWorld(
        canvas,
        options || {},
        "WebGL unavailable; using the 2D artwork fallback.",
      );
    }
    return activeWorld;
  }

  const publicApi = {
    mount,
    apply(worldState) {
      return activeWorld ? activeWorld.apply(worldState) : null;
    },
    preview(option) {
      return activeWorld ? activeWorld.preview(option) : null;
    },
    clearPreview() {
      if (activeWorld) activeWorld.clearPreview();
    },
    setPointer(x, y) {
      if (activeWorld) activeWorld.setPointer(x, y);
    },
    destroy() {
      if (!activeWorld) return;
      const world = activeWorld;
      activeWorld = null;
      world.destroy();
    },
  };

  global.LastWordsWorld = publicApi;
})(typeof window !== "undefined" ? window : globalThis);
