#!/usr/bin/env python3
"""
Build the 60-second LAST WORDS judging video from real browser captures.

The script never recreates the artwork in Pillow or ffmpeg. Product footage
comes only from Playwright pages served by the real FastAPI application.
Pillow is used for typography-only title/caption cards, and ffmpeg is used
for trimming, split-screen comparison, captions, and final encoding.

Default flow:
  1. create an isolated SQLite database;
  2. start a local uvicorn process against that database;
  3. record a living world and hover preview;
  4. record one real sacrifice in two browser contexts;
  5. prepare the same demo database until exactly one law remains;
  6. perform the twentieth sacrifice through the real UI;
  7. record the immutable WORLD 001 archive and WORLD 002 rebirth;
  8. assemble an exactly 60-second 1280x720 H.264 MP4.

Run from the project root:

    python3 capture/capture_submission.py

Use an already-running isolated server:

    python3 capture/capture_submission.py \
      --base-url http://127.0.0.1:8787 \
      --db /absolute/path/to/demo.sqlite3

Never point --db at lastwords.db. The script refuses that production-shaped
path because it intentionally rewrites the demo world.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError as exc:  # pragma: no cover - dependency preflight
    raise SystemExit(
        "Pillow is required. Run: python3 -m pip install -r capture/requirements.txt"
    ) from exc

try:
    from playwright.sync_api import (
        Browser,
        BrowserContext,
        Page,
        TimeoutError as PlaywrightTimeout,
        sync_playwright,
    )
except ImportError as exc:  # pragma: no cover - dependency preflight
    raise SystemExit(
        "Playwright is required. Run: python3 -m pip install -r "
        "capture/requirements.txt && playwright install chromium"
    ) from exc


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CAPTURE_ROOT = Path(__file__).resolve().parent
DEFAULT_WORK_DIR = CAPTURE_ROOT / "submission_build"
DEFAULT_OUTPUT = DEFAULT_WORK_DIR / "LAST_WORDS_60s.mp4"
PRODUCTION_DB = PROJECT_ROOT / "lastwords.db"

WIDTH = 1280
HEIGHT = 720
FPS = 30
FINAL_DURATION_SECONDS = 60.0

VIEWPORT = {"width": WIDTH, "height": HEIGHT}
RAW_NAMES = (
    "intro.webm",
    "mutation-a.webm",
    "mutation-b.webm",
    "ending.webm",
    "archive-rebirth.webm",
)


@dataclass(frozen=True)
class Segment:
    slug: str
    duration: float
    source: Path | None
    overlay: Path | None = None
    start: float = 0.0
    transform: str = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture and assemble the actual-screen 60-second demo."
    )
    parser.add_argument(
        "--base-url",
        default="",
        help=(
            "Use an existing isolated server instead of starting uvicorn. "
            "The server must use the database passed with --db."
        ),
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Isolated demo SQLite path (default: <work-dir>/demo.sqlite3).",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=DEFAULT_WORK_DIR,
        help="Raw captures, cards, segments, logs, and manifest directory.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Final MP4 path.",
    )
    parser.add_argument("--port", type=int, default=8791)
    parser.add_argument(
        "--rebirth-seconds",
        type=float,
        default=5.0,
        help="Mourning interval in the isolated demo world.",
    )
    parser.add_argument(
        "--live-url",
        default="",
        help="Optional public artwork URL shown on the final card.",
    )
    parser.add_argument(
        "--repo-url",
        default="",
        help="Optional public source URL shown on the final card.",
    )
    parser.add_argument(
        "--allow-live-ai",
        action="store_true",
        help=(
            "Keep provider API keys in the spawned server. The default removes "
            "them so capture timing uses the deterministic local fallback."
        ),
    )
    parser.add_argument(
        "--headful",
        action="store_true",
        help="Show Chromium windows while recording.",
    )
    parser.add_argument(
        "--silent",
        action="store_true",
        help="Do not add the low procedural audio bed.",
    )
    parser.add_argument(
        "--keep-existing-db",
        action="store_true",
        help=(
            "Do not recreate the isolated demo DB. Intended only for debugging "
            "a failed capture; normal submission builds should start fresh."
        ),
    )
    return parser.parse_args()


def run(
    args: Iterable[str | os.PathLike[str]],
    *,
    cwd: Path = PROJECT_ROOT,
    env: dict[str, str] | None = None,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    command = [str(item) for item in args]
    print("+", " ".join(command))
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=True,
        text=True,
        capture_output=capture_output,
    )


def require_program(name: str) -> str:
    resolved = shutil.which(name)
    if not resolved:
        raise SystemExit(f"{name} is required but was not found on PATH")
    return resolved


def normalize_path(path: Path) -> Path:
    return path.expanduser().resolve()


def guard_demo_db(db_path: Path) -> None:
    db_path = normalize_path(db_path)
    production = PRODUCTION_DB.resolve()
    if db_path == production:
        raise SystemExit(
            f"refusing to use the live project database: {production}\n"
            "Choose an isolated path such as capture/submission_build/demo.sqlite3."
        )
    if db_path.name == "lastwords.db":
        raise SystemExit(
            "refusing a database named lastwords.db; use an unmistakable demo name"
        )


def remove_sqlite_files(db_path: Path) -> None:
    for candidate in (
        db_path,
        Path(f"{db_path}-wal"),
        Path(f"{db_path}-shm"),
    ):
        if candidate.exists():
            candidate.unlink()


def json_get(url: str, timeout: float = 5.0) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "lastwords-capture/1"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_for_server(base_url: str, timeout: float = 35.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            return json_get(f"{base_url}/api/state")
        except (OSError, ValueError, urllib.error.URLError) as exc:
            last_error = exc
            time.sleep(0.25)
    raise RuntimeError(f"server did not become ready: {last_error}")


def wait_for_edition(
    base_url: str,
    edition_number: int,
    timeout: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    latest: dict[str, Any] = {}
    while time.monotonic() < deadline:
        latest = json_get(f"{base_url}/api/state")
        if int(latest.get("edition", {}).get("number", 0)) >= edition_number:
            return latest
        time.sleep(0.35)
    raise RuntimeError(
        f"WORLD {edition_number:03d} was not born within {timeout:.1f}s; "
        f"latest edition payload: {latest.get('edition')}"
    )


def server_environment(db_path: Path, rebirth_seconds: float) -> dict[str, str]:
    env = os.environ.copy()
    env["LASTWORDS_DB"] = str(db_path)
    env["LASTWORDS_EDITION_REBIRTH_SECONDS"] = str(rebirth_seconds)
    env["LASTWORDS_END_THRESHOLD"] = "0"
    env["LASTWORDS_GLOBAL_MESSAGES_PER_MINUTE"] = "200"
    return env


def start_server(
    *,
    port: int,
    env: dict[str, str],
    log_path: Path,
) -> subprocess.Popen[str]:
    log_handle = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=PROJECT_ROOT,
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
    )
    process._lastwords_log_handle = log_handle  # type: ignore[attr-defined]
    return process


def stop_server(process: subprocess.Popen[str] | None) -> None:
    if process is None:
        return
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    handle = getattr(process, "_lastwords_log_handle", None)
    if handle is not None:
        handle.close()


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def state_snapshot(base_url: str, snapshots_dir: Path, name: str) -> dict[str, Any]:
    value = json_get(f"{base_url}/api/state")
    write_json(snapshots_dir / f"{name}.json", value)
    return value


def close_and_save_video(
    context: BrowserContext,
    page: Page,
    destination: Path,
) -> None:
    video = page.video
    context.close()
    if video is None:
        raise RuntimeError(f"Playwright did not attach a video to {destination.name}")
    video.save_as(str(destination))
    if not destination.exists() or destination.stat().st_size == 0:
        raise RuntimeError(f"empty browser recording: {destination}")


def create_video_context(
    browser: Browser,
    raw_dir: Path,
) -> tuple[BrowserContext, Page]:
    context = browser.new_context(
        viewport=VIEWPORT,
        device_scale_factor=1,
        record_video_dir=str(raw_dir),
        record_video_size=VIEWPORT,
        color_scheme="dark",
        reduced_motion="no-preference",
    )
    return context, context.new_page()


def wait_for_art(page: Page, base_url: str) -> None:
    page.goto(base_url, wait_until="domcontentloaded", timeout=30_000)
    page.locator(".sacrifice-option").first.wait_for(
        state="visible",
        timeout=20_000,
    )
    page.wait_for_function(
        """
        () => {
          const count = document.querySelector("#alive-count")?.textContent?.trim();
          return count && count !== "—" && count !== "&mdash;";
        }
        """,
        timeout=15_000,
    )
    page.wait_for_timeout(1_100)


def choose_visual_option(page: Page) -> Any:
    options = page.locator(".sacrifice-option")
    count = options.count()
    if count < 1:
        raise RuntimeError("the live page offered no sacrifice option")
    preferred = (
        "gravity",
        "attraction",
        "shape",
        "turbulence",
        "orbit",
        "color",
        "sound",
    )
    option_texts = [options.nth(i).inner_text().lower() for i in range(count)]
    for keyword in preferred:
        for index, text in enumerate(option_texts):
            if keyword in text:
                return options.nth(index)
    return options.first


def record_intro(
    browser: Browser,
    base_url: str,
    raw_dir: Path,
) -> Path:
    context, page = create_video_context(browser, raw_dir)
    wait_for_art(page, base_url)
    option = choose_visual_option(page)
    option.hover()
    page.wait_for_timeout(2_200)
    option.click()
    page.wait_for_timeout(2_400)
    canvas = page.locator("#world-canvas")
    box = canvas.bounding_box()
    if box:
        page.mouse.move(
            box["x"] + box["width"] * 0.72,
            box["y"] + box["height"] * 0.33,
            steps=20,
        )
    page.wait_for_timeout(2_000)
    destination = raw_dir / "intro.webm"
    close_and_save_video(context, page, destination)
    return destination


def record_mutation_pair(
    browser: Browser,
    base_url: str,
    raw_dir: Path,
) -> tuple[Path, Path, dict[str, Any]]:
    context_a, page_a = create_video_context(browser, raw_dir)
    context_b, page_b = create_video_context(browser, raw_dir)
    wait_for_art(page_a, base_url)
    wait_for_art(page_b, base_url)

    before = json_get(f"{base_url}/api/state")
    before_version = int(before.get("world", {}).get("version", 0))
    option = choose_visual_option(page_a)
    option.hover()
    page_a.wait_for_timeout(1_100)
    option.click()
    page_a.fill(
        "#message-input",
        "What do you become when this law is gone?",
    )
    page_a.wait_for_timeout(1_100)

    with page_a.expect_response(
        lambda response: response.request.method == "POST"
        and response.url.endswith("/api/message"),
        timeout=35_000,
    ) as response_info:
        page_a.click("#send-button")
    response = response_info.value
    if not response.ok:
        raise RuntimeError(
            f"real sacrifice request failed: HTTP {response.status} "
            f"{response.text()[:300]}"
        )
    payload = response.json()
    new_version = int(payload.get("world", {}).get("version", before_version + 1))

    page_a.wait_for_function(
        """
        version => document.querySelector("#build-label")
          ?.textContent?.includes(String(version).padStart(4, "0"))
        """,
        arg=new_version,
        timeout=15_000,
    )
    page_b.wait_for_function(
        """
        version => document.querySelector("#build-label")
          ?.textContent?.includes(String(version).padStart(4, "0"))
        """,
        arg=new_version,
        timeout=15_000,
    )
    # Both contexts keep recording while either page waits.
    page_a.wait_for_timeout(10_000)

    destination_a = raw_dir / "mutation-a.webm"
    destination_b = raw_dir / "mutation-b.webm"
    video_a = page_a.video
    video_b = page_b.video
    context_a.close()
    context_b.close()
    if video_a is None or video_b is None:
        raise RuntimeError("two-browser capture did not produce both videos")
    video_a.save_as(str(destination_a))
    video_b.save_as(str(destination_b))
    return destination_a, destination_b, payload


PREPARE_FINAL_CODE = r"""
import json
import app

removed = []
with app.get_db() as conn:
    while True:
        world = app.get_world_state(conn)
        active = [
            law for law in app.INITIAL_WORLD_GENOME
            if abs(float(world["genome"].get(law, 0.0))) > 1e-9
        ]
        if len(active) <= 1:
            break
        options = app.get_sacrifice_options(conn, world)
        if not options:
            raise RuntimeError(f"no sacrifice option with {len(active)} laws active")
        result = app.sacrifice_world_law(conn, options[0]["word"])
        removed.append(result)
    final_world = app.get_world_state(conn)
    active = [
        law for law in app.INITIAL_WORLD_GENOME
        if abs(float(final_world["genome"].get(law, 0.0))) > 1e-9
    ]
print(json.dumps({
    "prepared": removed,
    "world_version": final_world["version"],
    "active_laws": active,
}))
"""


def prepare_final_world(
    env: dict[str, str],
    snapshots_dir: Path,
) -> dict[str, Any]:
    completed = run(
        [sys.executable, "-c", PREPARE_FINAL_CODE],
        env=env,
        capture_output=True,
    )
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("final-world preparation returned no receipt")
    receipt = json.loads(lines[-1])
    if len(receipt.get("active_laws", [])) != 1:
        raise RuntimeError(f"expected one active law: {receipt}")
    write_json(snapshots_dir / "prepared-final-law.json", receipt)
    return receipt


def record_ending(
    browser: Browser,
    base_url: str,
    raw_dir: Path,
) -> tuple[Path, dict[str, Any]]:
    context, page = create_video_context(browser, raw_dir)
    wait_for_art(page, base_url)
    option = page.locator(".sacrifice-option").first
    option.hover()
    page.wait_for_timeout(900)
    option.click()
    page.fill("#message-input", "What remains after your final law is gone?")
    page.wait_for_timeout(900)

    with page.expect_response(
        lambda response: response.request.method == "POST"
        and response.url.endswith("/api/message"),
        timeout=35_000,
    ) as response_info:
        page.click("#send-button")
    response = response_info.value
    if not response.ok:
        raise RuntimeError(
            f"twentieth sacrifice failed: HTTP {response.status} "
            f"{response.text()[:300]}"
        )
    payload = response.json()
    if not payload.get("silenced"):
        raise RuntimeError(
            "the prepared final sacrifice did not silence WORLD 001; "
            f"payload edition={payload.get('edition')}"
        )
    page.locator("#silence-block").wait_for(state="visible", timeout=20_000)
    page.wait_for_timeout(4_200)
    destination = raw_dir / "ending.webm"
    close_and_save_video(context, page, destination)
    return destination, payload


def record_archive_and_rebirth(
    browser: Browser,
    base_url: str,
    raw_dir: Path,
) -> Path:
    context, page = create_video_context(browser, raw_dir)
    page.goto(f"{base_url}/remains", wait_until="domcontentloaded", timeout=30_000)
    try:
        page.wait_for_function(
            "() => document.body.innerText.includes('WORLD 001')",
            timeout=15_000,
        )
    except PlaywrightTimeout as exc:
        raise RuntimeError(
            "the archive UI is not ready: /remains must visibly render WORLD 001"
        ) from exc
    page.wait_for_timeout(3_100)

    page.goto(base_url, wait_until="domcontentloaded", timeout=30_000)
    try:
        page.wait_for_function(
            "() => document.body.innerText.includes('WORLD 002')",
            timeout=15_000,
        )
    except PlaywrightTimeout as exc:
        raise RuntimeError(
            "the rebirth UI is not ready: the main page must visibly render WORLD 002"
        ) from exc
    page.locator(".sacrifice-option").first.wait_for(
        state="visible",
        timeout=15_000,
    )
    page.wait_for_timeout(3_200)
    destination = raw_dir / "archive-rebirth.webm"
    close_and_save_video(context, page, destination)
    return destination


def find_font(*, bold: bool = False) -> Path:
    candidates = (
        (
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/System/Library/Fonts/SFNSMono.ttf",
            "/System/Library/Fonts/Menlo.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        )
        if bold
        else (
            "/System/Library/Fonts/SFNSMono.ttf",
            "/System/Library/Fonts/Menlo.ttc",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        )
    )
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return path
    raise RuntimeError("no usable system font found for title and caption cards")


def font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(find_font(bold=bold)), size=size)


def wrap_by_width(
    draw: ImageDraw.ImageDraw,
    text: str,
    selected_font: ImageFont.FreeTypeFont,
    max_width: int,
) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        bounds = draw.textbbox((0, 0), candidate, font=selected_font)
        if current and bounds[2] - bounds[0] > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def render_centered_lines(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    selected_font: ImageFont.FreeTypeFont,
    *,
    top: int,
    fill: tuple[int, int, int, int],
    gap: int = 12,
) -> int:
    y = top
    for line in lines:
        bounds = draw.textbbox((0, 0), line, font=selected_font)
        width = bounds[2] - bounds[0]
        height = bounds[3] - bounds[1]
        draw.text(
            ((WIDTH - width) / 2, y - bounds[1]),
            line,
            font=selected_font,
            fill=fill,
        )
        y += height + gap
    return y


def make_title_card(path: Path) -> None:
    image = Image.new("RGBA", (WIDTH, HEIGHT), (7, 8, 8, 255))
    draw = ImageDraw.Draw(image, "RGBA")
    draw.rectangle((88, 104, 94, 616), fill=(191, 42, 38, 255))
    draw.text(
        (124, 106),
        "A SELF-ERASING WORLD",
        font=font(18, bold=True),
        fill=(191, 42, 38, 255),
    )
    draw.text(
        (120, 183),
        "LAST WORDS",
        font=font(72, bold=True),
        fill=(239, 235, 221, 255),
    )
    subtitle_font = font(31)
    lines = wrap_by_width(
        draw,
        "Every visitor deletes one executable law from the same living artwork.",
        subtitle_font,
        900,
    )
    y = 304
    for line in lines:
        draw.text(
            (124, y),
            line,
            font=subtitle_font,
            fill=(204, 199, 184, 255),
        )
        y += 48
    draw.text(
        (124, 570),
        "THE ART DOES NOT DEPICT LOSS. IT PERFORMS IT.",
        font=font(19, bold=True),
        fill=(140, 137, 126, 255),
    )
    image.convert("RGB").save(path, quality=95)


def make_end_card(path: Path, live_url: str, repo_url: str) -> None:
    image = Image.new("RGBA", (WIDTH, HEIGHT), (7, 8, 8, 255))
    draw = ImageDraw.Draw(image, "RGBA")
    draw.text(
        (80, 76),
        "WORLD 001 IS DEAD.",
        font=font(48, bold=True),
        fill=(239, 235, 221, 255),
    )
    draw.text(
        (80, 150),
        "ITS REMAINS ARE STILL PUBLIC.",
        font=font(34),
        fill=(191, 42, 38, 255),
    )
    draw.text(
        (80, 250),
        "WORLD 002 HAS BEGUN.",
        font=font(48, bold=True),
        fill=(239, 235, 221, 255),
    )
    draw.line((80, 340, 1200, 340), fill=(75, 74, 68, 255), width=1)
    draw.text(
        (80, 382),
        "One shared organism · twenty executable laws · irreversible public memory",
        font=font(22),
        fill=(179, 175, 162, 255),
    )
    link_y = 520
    if live_url:
        draw.text(
            (80, link_y),
            live_url,
            font=font(17),
            fill=(216, 211, 197, 255),
        )
        link_y += 34
    if repo_url:
        draw.text(
            (80, link_y),
            repo_url,
            font=font(17),
            fill=(216, 211, 197, 255),
        )
    image.convert("RGB").save(path, quality=95)


def make_caption_overlay(
    path: Path,
    label: str,
    headline: str,
    detail: str,
    *,
    split_labels: bool = False,
) -> None:
    image = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image, "RGBA")
    draw.rounded_rectangle(
        (28, 24, 318, 62),
        radius=4,
        fill=(7, 8, 8, 220),
        outline=(191, 42, 38, 230),
        width=1,
    )
    draw.text(
        (44, 33),
        label,
        font=font(16, bold=True),
        fill=(239, 235, 221, 255),
    )
    if split_labels:
        draw.text(
            (246, 138),
            "VISITOR A",
            font=font(16, bold=True),
            fill=(239, 235, 221, 255),
        )
        draw.text(
            (886, 138),
            "VISITOR B",
            font=font(16, bold=True),
            fill=(239, 235, 221, 255),
        )
    draw.rectangle((0, 564, WIDTH, HEIGHT), fill=(7, 8, 8, 226))
    draw.rectangle((0, 564, 7, HEIGHT), fill=(191, 42, 38, 255))
    draw.text(
        (38, 586),
        headline,
        font=font(27, bold=True),
        fill=(239, 235, 221, 255),
    )
    detail_font = font(17)
    lines = wrap_by_width(draw, detail, detail_font, WIDTH - 80)[:2]
    y = 630
    for line in lines:
        draw.text(
            (39, y),
            line,
            font=detail_font,
            fill=(190, 186, 173, 255),
        )
        y += 27
    image.save(path)


def build_cards(cards_dir: Path, live_url: str, repo_url: str) -> dict[str, Path]:
    cards_dir.mkdir(parents=True, exist_ok=True)
    title = cards_dir / "title.png"
    ending = cards_dir / "end.png"
    make_title_card(title)
    make_end_card(ending, live_url, repo_url)

    captions = {
        "offer": (
            "01 / THE OFFER",
            "EVERY LIVING WORD CARRIES A LAW.",
            "Hovering previews the loss. Nothing changes until a visitor chooses.",
            False,
        ),
        "mutation": (
            "02 / THE SACRIFICE",
            "THE AUDIENCE CHANGES THE NEXT SCENE.",
            "A real message deletes one law, changes the shared genome, and forces a live rebuild.",
            False,
        ),
        "code": (
            "03 / EXECUTABLE ART",
            "THE CHOSEN LAW DISAPPEARS FROM ACTUAL GLSL.",
            "The shader source changes and recompiles in the browser. The receipt is part of the artwork.",
            False,
        ),
        "sync": (
            "04 / ONE SHARED ORGANISM",
            "A SECOND VISITOR RECEIVES THE SAME WOUND.",
            "Two independent browser sessions converge on the same build without replaying a fake animation.",
            True,
        ),
        "death": (
            "05 / THE TWENTIETH LAW",
            "THE WORLD USES ITS FINAL LAW TO SAY GOODBYE.",
            "The last sacrifice ends WORLD 001. Its final message and every wound become immutable remains.",
            False,
        ),
        "archive": (
            "06 / DEATH WITHOUT RESET",
            "WORLD 001 STAYS DEAD. WORLD 002 IS BORN.",
            "A new organism begins, while the previous world's genome, graveyard, and last words remain public.",
            False,
        ),
    }
    result = {"title": title, "end": ending}
    for slug, (label, headline, detail, split) in captions.items():
        target = cards_dir / f"caption-{slug}.png"
        make_caption_overlay(
            target,
            label,
            headline,
            detail,
            split_labels=split,
        )
        result[slug] = target
    return result


def encode_card_segment(
    ffmpeg: str,
    image: Path,
    destination: Path,
    duration: float,
) -> None:
    run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-loop",
            "1",
            "-framerate",
            str(FPS),
            "-i",
            image,
            "-t",
            f"{duration:.3f}",
            "-vf",
            f"scale={WIDTH}:{HEIGHT},fps={FPS},format=yuv420p",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            destination,
        ]
    )


def encode_actual_segment(
    ffmpeg: str,
    segment: Segment,
    destination: Path,
) -> None:
    if segment.source is None or segment.overlay is None:
        raise ValueError(f"actual segment is missing source/overlay: {segment.slug}")
    base_transform = (
        f"trim=start={segment.start:.3f},setpts=PTS-STARTPTS,"
        f"{segment.transform or f'scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2'},"
        f"fps={FPS},tpad=stop_mode=clone:stop_duration={segment.duration:.3f},"
        f"trim=duration={segment.duration:.3f}[base];"
        f"[base][1:v]overlay=0:0:shortest=1,format=yuv420p[outv]"
    )
    run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            segment.source,
            "-loop",
            "1",
            "-framerate",
            str(FPS),
            "-i",
            segment.overlay,
            "-filter_complex",
            base_transform,
            "-map",
            "[outv]",
            "-t",
            f"{segment.duration:.3f}",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            destination,
        ]
    )


def encode_split_segment(
    ffmpeg: str,
    left: Path,
    right: Path,
    overlay: Path,
    destination: Path,
    duration: float,
    start: float,
) -> None:
    graph = (
        f"[0:v]trim=start={start:.3f},setpts=PTS-STARTPTS,"
        f"scale=640:360,fps={FPS},"
        f"tpad=stop_mode=clone:stop_duration={duration:.3f},"
        f"trim=duration={duration:.3f}[left];"
        f"[1:v]trim=start={start:.3f},setpts=PTS-STARTPTS,"
        f"scale=640:360,fps={FPS},"
        f"tpad=stop_mode=clone:stop_duration={duration:.3f},"
        f"trim=duration={duration:.3f}[right];"
        f"color=c=#070808:s={WIDTH}x{HEIGHT}:r={FPS}:d={duration:.3f}[bg];"
        "[bg][left]overlay=0:150[tmp];"
        "[tmp][right]overlay=640:150[twoup];"
        "[twoup][2:v]overlay=0:0:shortest=1,format=yuv420p[outv]"
    )
    run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            left,
            "-i",
            right,
            "-loop",
            "1",
            "-framerate",
            str(FPS),
            "-i",
            overlay,
            "-filter_complex",
            graph,
            "-map",
            "[outv]",
            "-t",
            f"{duration:.3f}",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            destination,
        ]
    )


def concat_line(path: Path) -> str:
    escaped = str(path.resolve()).replace("'", "'\\''")
    return f"file '{escaped}'"


def assemble_final(
    ffmpeg: str,
    ffprobe: str,
    segments: list[Path],
    destination: Path,
    *,
    silent: bool,
) -> dict[str, Any]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    concat_path = segments[0].parent / "concat.txt"
    concat_path.write_text(
        "\n".join(concat_line(path) for path in segments) + "\n",
        encoding="utf-8",
    )
    common = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        concat_path,
    ]
    if silent:
        command = common + [
            "-t",
            "60.000",
            "-an",
            "-vf",
            f"fps={FPS},format=yuv420p",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-movflags",
            "+faststart",
            destination,
        ]
    else:
        command = common + [
            "-f",
            "lavfi",
            "-t",
            "60.000",
            "-i",
            "anoisesrc=color=pink:amplitude=0.025:sample_rate=48000",
            "-f",
            "lavfi",
            "-t",
            "60.000",
            "-i",
            "sine=frequency=55:sample_rate=48000",
            "-filter_complex",
            (
                "[1:a]lowpass=f=780,volume=0.04[noise];"
                "[2:a]volume=0.009[tone];"
                "[noise][tone]amix=inputs=2:normalize=0,"
                "afade=t=in:st=0:d=2,afade=t=out:st=57:d=3[aout]"
            ),
            "-map",
            "0:v:0",
            "-map",
            "[aout]",
            "-t",
            "60.000",
            "-vf",
            f"fps={FPS},format=yuv420p",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            destination,
        ]
    run(command)

    probe = run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_name,width,height,r_frame_rate",
            "-of",
            "json",
            destination,
        ],
        capture_output=True,
    )
    metadata = json.loads(probe.stdout)
    streams = metadata.get("streams", [])
    video_stream = next(
        (stream for stream in streams if stream.get("width")),
        {},
    )
    duration = float(metadata.get("format", {}).get("duration", 0.0))
    if video_stream.get("codec_name") != "h264":
        raise RuntimeError(f"final codec is not H.264: {video_stream}")
    if (
        int(video_stream.get("width", 0)) != WIDTH
        or int(video_stream.get("height", 0)) != HEIGHT
    ):
        raise RuntimeError(f"final dimensions are not {WIDTH}x{HEIGHT}: {video_stream}")
    if not 59.95 <= duration <= 60.05:
        raise RuntimeError(f"final duration is not 60 seconds: {duration:.3f}")
    return metadata


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_video(
    *,
    ffmpeg: str,
    ffprobe: str,
    raw_dir: Path,
    cards: dict[str, Path],
    segments_dir: Path,
    destination: Path,
    silent: bool,
) -> tuple[list[Path], dict[str, Any]]:
    segments_dir.mkdir(parents=True, exist_ok=True)
    outputs = [segments_dir / f"{index:02d}-{slug}.mp4" for index, slug in enumerate(
        (
            "title",
            "offer",
            "mutation",
            "code",
            "sync",
            "death",
            "archive",
            "end",
        )
    )]

    encode_card_segment(ffmpeg, cards["title"], outputs[0], 4.0)
    encode_actual_segment(
        ffmpeg,
        Segment(
            "offer",
            7.0,
            raw_dir / "intro.webm",
            cards["offer"],
            start=0.6,
        ),
        outputs[1],
    )
    encode_actual_segment(
        ffmpeg,
        Segment(
            "mutation",
            13.0,
            raw_dir / "mutation-a.webm",
            cards["mutation"],
            start=0.7,
        ),
        outputs[2],
    )
    encode_actual_segment(
        ffmpeg,
        Segment(
            "code",
            8.0,
            raw_dir / "mutation-a.webm",
            cards["code"],
            start=4.0,
            transform="crop=720:400:540:50,scale=1280:720",
        ),
        outputs[3],
    )
    encode_split_segment(
        ffmpeg,
        raw_dir / "mutation-a.webm",
        raw_dir / "mutation-b.webm",
        cards["sync"],
        outputs[4],
        duration=8.0,
        start=3.3,
    )
    encode_actual_segment(
        ffmpeg,
        Segment(
            "death",
            11.0,
            raw_dir / "ending.webm",
            cards["death"],
            start=0.5,
        ),
        outputs[5],
    )
    encode_actual_segment(
        ffmpeg,
        Segment(
            "archive",
            6.0,
            raw_dir / "archive-rebirth.webm",
            cards["archive"],
            start=0.4,
        ),
        outputs[6],
    )
    encode_card_segment(ffmpeg, cards["end"], outputs[7], 3.0)

    total = 4 + 7 + 13 + 8 + 8 + 11 + 6 + 3
    if total != 60:
        raise AssertionError(f"timeline no longer totals 60 seconds: {total}")
    metadata = assemble_final(
        ffmpeg,
        ffprobe,
        outputs,
        destination,
        silent=silent,
    )
    return outputs, metadata


def main() -> int:
    args = parse_args()
    ffmpeg = require_program("ffmpeg")
    ffprobe = require_program("ffprobe")

    work_dir = normalize_path(args.work_dir)
    raw_dir = work_dir / "raw"
    cards_dir = work_dir / "cards"
    segments_dir = work_dir / "segments"
    snapshots_dir = work_dir / "snapshots"
    output = normalize_path(args.output)
    db_path = normalize_path(args.db or (work_dir / "demo.sqlite3"))
    guard_demo_db(db_path)

    for directory in (
        work_dir,
        raw_dir,
        cards_dir,
        segments_dir,
        snapshots_dir,
        output.parent,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    for name in RAW_NAMES:
        path = raw_dir / name
        if path.exists():
            path.unlink()
    if not args.keep_existing_db:
        remove_sqlite_files(db_path)

    env = server_environment(db_path, args.rebirth_seconds)
    if not args.allow_live_ai:
        env.pop("GEMINI_API_KEY", None)
        env.pop("ANTHROPIC_API_KEY", None)

    server: subprocess.Popen[str] | None = None
    base_url = args.base_url.rstrip("/")
    if not base_url:
        base_url = f"http://127.0.0.1:{args.port}"
        server = start_server(
            port=args.port,
            env=env,
            log_path=work_dir / "server.log",
        )

    started_at = datetime.now(timezone.utc).isoformat()
    try:
        initial = wait_for_server(base_url)
        write_json(snapshots_dir / "00-initial.json", initial)
        if int(initial.get("edition", {}).get("number", 0)) != 1:
            raise RuntimeError(
                "submission capture must begin with a fresh WORLD 001; "
                f"received {initial.get('edition')}"
            )

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=not args.headful)
            try:
                record_intro(browser, base_url, raw_dir)
                mutation_a, mutation_b, mutation_payload = record_mutation_pair(
                    browser,
                    base_url,
                    raw_dir,
                )
                write_json(
                    snapshots_dir / "01-real-sacrifice-response.json",
                    mutation_payload,
                )
                state_snapshot(base_url, snapshots_dir, "02-after-real-sacrifice")

                preparation = prepare_final_world(env, snapshots_dir)
                prepared_state = state_snapshot(
                    base_url,
                    snapshots_dir,
                    "03-one-law-remains",
                )
                active_laws = [
                    law
                    for law, value in prepared_state.get("world", {})
                    .get("genome", {})
                    .items()
                    if abs(float(value)) > 1e-9
                ]
                if len(active_laws) != 1:
                    raise RuntimeError(
                        f"demo DB did not reach one active law: {active_laws}"
                    )

                ending_video, ending_payload = record_ending(
                    browser,
                    base_url,
                    raw_dir,
                )
                write_json(
                    snapshots_dir / "04-twentieth-sacrifice-response.json",
                    ending_payload,
                )
                state_snapshot(base_url, snapshots_dir, "05-world-001-dead")

                world_002 = wait_for_edition(
                    base_url,
                    2,
                    timeout=max(20.0, args.rebirth_seconds + 15.0),
                )
                write_json(snapshots_dir / "06-world-002-born.json", world_002)
                record_archive_and_rebirth(browser, base_url, raw_dir)
            finally:
                browser.close()

        cards = build_cards(cards_dir, args.live_url, args.repo_url)
        segment_paths, metadata = build_video(
            ffmpeg=ffmpeg,
            ffprobe=ffprobe,
            raw_dir=raw_dir,
            cards=cards,
            segments_dir=segments_dir,
            destination=output,
            silent=args.silent,
        )
        manifest = {
            "title": "LAST WORDS — 60-second submission demo",
            "captured_at": started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "base_url": base_url,
            "database": str(db_path),
            "output": str(output),
            "sha256": sha256(output),
            "duration_seconds": FINAL_DURATION_SECONDS,
            "dimensions": [WIDTH, HEIGHT],
            "fps": FPS,
            "codec": "H.264",
            "artwork_footage": (
                "All product/artwork shots are direct Playwright recordings "
                "of the real FastAPI app. Pillow cards contain typography only."
            ),
            "timeline": [
                {"seconds": "00-04", "scene": "title card"},
                {"seconds": "04-11", "scene": "live world and hover preview"},
                {"seconds": "11-24", "scene": "real sacrifice and mutation"},
                {"seconds": "24-32", "scene": "actual GLSL diff and compile"},
                {"seconds": "32-40", "scene": "two real browser sessions sync"},
                {"seconds": "40-51", "scene": "twentieth law and WORLD 001 death"},
                {"seconds": "51-57", "scene": "archive and WORLD 002 rebirth"},
                {"seconds": "57-60", "scene": "end card"},
            ],
            "raw_recordings": [str(raw_dir / name) for name in RAW_NAMES],
            "encoded_segments": [str(path) for path in segment_paths],
            "ffprobe": metadata,
        }
        write_json(work_dir / "manifest.json", manifest)
        print(f"\nSubmission video complete: {output}")
        print(f"SHA-256: {manifest['sha256']}")
        return 0
    finally:
        stop_server(server)


if __name__ == "__main__":
    raise SystemExit(main())
