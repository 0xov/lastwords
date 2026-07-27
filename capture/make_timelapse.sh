#!/usr/bin/env bash
#
# make_timelapse.sh — LAST WORDS
#
# Concatenates every captures/<date>/capture.webm (in date order) into one
# timelapse.mp4 (H.264, 1280x800). Each segment is labeled with its date and
# that day's alive-word count, read from captures/<date>/state.json, drawn
# as an overlay for the whole segment.
#
# Usage:
#   bash capture/make_timelapse.sh [captures_dir] [output_path]
#
# Defaults: captures_dir=captures, output_path=<captures_dir>/timelapse.mp4
#
# Requires: ffmpeg.
# Optional: jq (falls back to python3, then a plain grep, to read
#   state.json if jq isn't installed).
#
# Design note: overlaying dynamic per-frame text on top of each clip is the
# most direct reading of "labeled segments", so that's what this script
# does, via ffmpeg's `concat` *filter* (not the demuxer) — the filter form
# re-encodes each input through its own scale/pad/drawtext chain before
# joining, so clips of differing resolution or codec never break the
# concatenation. The one genuinely fragile part is drawtext needing a real
# font file: some CI images (and bare-bones Linux boxes) ship no fonts at
# all. Rather than fail the whole timelapse over a missing font, this
# script searches a short list of common font paths and — if none exist —
# degrades gracefully to a label-free concat (still scaled/padded to
# 1280x800, still a valid timelapse.mp4) with a clear warning on stderr.
# That's the "acceptable fallback" the spec allows for, applied per-run
# rather than needing a separate code path.

set -euo pipefail

CAPTURES_DIR="${1:-captures}"
OUTPUT_PATH="${2:-${CAPTURES_DIR%/}/timelapse.mp4}"
WIDTH=1280
HEIGHT=800

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "error: ffmpeg is not installed. Install it (e.g. 'brew install ffmpeg' or" >&2
  echo "'apt-get install ffmpeg') and re-run this script." >&2
  exit 1
fi

if [ ! -d "$CAPTURES_DIR" ]; then
  echo "error: captures directory not found: $CAPTURES_DIR" >&2
  exit 1
fi

# --- collect capture.webm files in date order --------------------------
# Directory names are YYYY-MM-DD, so a plain lexicographic sort is also
# chronological order. Avoid `mapfile`/`readarray` (bash 4+ only) so this
# still runs under macOS's stock bash 3.2.

DAY_DIRS=()
while IFS= read -r d; do
  DAY_DIRS+=("$d")
done < <(find "$CAPTURES_DIR" -mindepth 1 -maxdepth 1 -type d -name '20*' | sort)

CLIPS=()
for d in "${DAY_DIRS[@]}"; do
  if [ -f "$d/capture.webm" ]; then
    CLIPS+=("$d")
  fi
done

if [ "${#CLIPS[@]}" -eq 0 ]; then
  echo "error: no captures/<date>/capture.webm files found under $CAPTURES_DIR" >&2
  exit 1
fi

echo "found ${#CLIPS[@]} capture(s):"
printf '  %s\n' "${CLIPS[@]}"

# --- read the alive count from a day's state.json -----------------------

read_alive_count() {
  local state_file="$1"
  if [ ! -f "$state_file" ]; then
    echo "?"
    return
  fi
  if command -v jq >/dev/null 2>&1; then
    jq -r '.alive // "?"' "$state_file" 2>/dev/null || echo "?"
  elif command -v python3 >/dev/null 2>&1; then
    python3 -c "
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    print(d.get('alive', '?'))
except Exception:
    print('?')
" "$state_file"
  else
    grep -o '"alive"[[:space:]]*:[[:space:]]*[0-9]*' "$state_file" 2>/dev/null \
      | grep -o '[0-9]*$' | head -1 || echo "?"
  fi
}

# --- find a monospace font file for drawtext (no fontconfig dependency) -

find_font() {
  local candidates=(
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
    "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf"
    "/usr/share/fonts/TTF/DejaVuSansMono.ttf"
    "/System/Library/Fonts/Supplemental/Courier New.ttf"
    "/System/Library/Fonts/Menlo.ttc"
    "/Library/Fonts/Courier New.ttf"
  )
  local f
  for f in "${candidates[@]}"; do
    if [ -f "$f" ]; then
      echo "$f"
      return
    fi
  done
  find /usr/share/fonts /System/Library/Fonts /Library/Fonts \
    \( -iname '*mono*.ttf' -o -iname '*mono*.ttc' \) 2>/dev/null | head -1
}

FONT="$(find_font || true)"
if ! ffmpeg -hide_banner -filters 2>/dev/null | grep -q drawtext; then
  echo "warning: this ffmpeg build has no drawtext filter — timelapse will have no date/word-count overlay" >&2
  FONT=""
elif [ -n "$FONT" ]; then
  echo "using font for overlay: $FONT"
else
  echo "warning: no monospace font found on this system — timelapse will have no date/word-count overlay" >&2
fi

# --- build the ffmpeg filter_complex graph -------------------------------
# Each input is scaled+padded to WIDTHxHEIGHT (so mismatched clip sizes
# never break concatenation), then (if a font was found) gets its label
# drawn on top for the whole segment, then all segments are joined with
# the concat *filter*.

INPUT_ARGS=()
FILTER=""
LABELS=""
i=0
for d in "${CLIPS[@]}"; do
  DATE_LABEL="$(basename "$d")"
  ALIVE="$(read_alive_count "$d/state.json")"
  INPUT_ARGS+=(-i "$d/capture.webm")

  CHAIN="[${i}:v]scale=${WIDTH}:${HEIGHT}:force_original_aspect_ratio=decrease,pad=${WIDTH}:${HEIGHT}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30"

  if [ -n "$FONT" ]; then
    TEXT="${DATE_LABEL}  |  ${ALIVE} words remaining"
    # ffmpeg's drawtext filter treats : and ' as syntax — escape them.
    TEXT_ESCAPED=$(printf '%s' "$TEXT" | sed -e "s/:/\\\\:/g" -e "s/'/\\\\'/g")
    CHAIN="${CHAIN},drawtext=fontfile='${FONT}':text='${TEXT_ESCAPED}':x=24:y=24:fontsize=28:fontcolor=white:box=1:boxcolor=black@0.55:boxborderw=10"
  fi

  FILTER="${FILTER}${CHAIN}[v${i}];"
  LABELS="${LABELS}[v${i}]"
  i=$((i + 1))
done

FILTER="${FILTER}${LABELS}concat=n=${i}:v=1:a=0[outv]"

echo "encoding $OUTPUT_PATH ..."
ffmpeg -y "${INPUT_ARGS[@]}" \
  -filter_complex "$FILTER" \
  -map "[outv]" \
  -c:v libx264 -pix_fmt yuv420p -preset medium -crf 20 \
  "$OUTPUT_PATH"

echo "done: $OUTPUT_PATH"
