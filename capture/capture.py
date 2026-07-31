#!/usr/bin/env python3
"""
capture.py — LAST WORDS daily video-capture pipeline

Records a short video (and two screenshots) of the deployed artwork so the
decay timelapse for the demo video assembles itself, one day at a time.

Env vars:
    LASTWORDS_URL     required, e.g. https://lastwords.onrender.com
    CAPTURE_DIR       optional, default ./captures
    CAPTURE_MESSAGE   optional; if set, the script types this into the
                      input and sends it, so the clip shows one live
                      scripted exchange after the latest funeral replay.

Output: {CAPTURE_DIR}/YYYY-MM-DD/
    capture.webm   ~25-35s screen recording (main page -> /remains)
    main.png       screenshot of the main page after the (optional) reply
    remains.png    full-page screenshot of /remains
    state.json     {date, captured_at, url, alive, total, message_count,
                    silenced} — the day's decay logged as data, not just video

Requires: playwright (see capture/requirements.txt) + a Chromium download
(`playwright install chromium`). Uses Playwright's own request context to
fetch /api/state, so no extra HTTP dependency is needed.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

VIEWPORT = {"width": 1280, "height": 800}

INITIAL_REPLAY_MAX_WAIT_S = 15
REPLY_MAX_WAIT_S = 20
POST_REPLY_PAUSE_MS = 2000
REMAINS_RENDER_WAIT_MS = 4000
SCROLL_DURATION_MS = 5000
SCROLL_STEPS = 20


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def wait_for_ai_message(page, prev_count: int, max_wait_s: float) -> None:
    """Wait for a new `.msg.ai .msg-line` to appear beyond `prev_count`,
    then poll until its text stops growing (typewriter finished). Best
    effort: on timeout we just move on so the capture still completes."""
    deadline = time.time() + max_wait_s
    selector = ".msg.ai .msg-line"

    while time.time() < deadline:
        if page.locator(selector).count() > prev_count:
            break
        time.sleep(0.3)
    else:
        print(f"warning: no new AI message appeared within {max_wait_s}s", file=sys.stderr)
        return

    last = None
    stable_count = 0
    while time.time() < deadline:
        texts = page.locator(selector).all_inner_texts()
        current = texts[-1] if texts else ""
        if current == last and current != "":
            stable_count += 1
            if stable_count >= 3:
                return
        else:
            stable_count = 0
        last = current
        time.sleep(0.4)

    print(f"warning: AI message text did not stabilize within {max_wait_s}s", file=sys.stderr)


def wait_for_class_removed(page, selector: str, cls: str, max_wait_s: float) -> bool:
    """Poll until `selector`'s class list no longer contains `cls`.
    Returns True if it happened, False on timeout (non-fatal)."""
    deadline = time.time() + max_wait_s
    while time.time() < deadline:
        try:
            class_attr = page.locator(selector).first.get_attribute("class") or ""
        except PlaywrightError:
            class_attr = ""
        if cls not in class_attr.split():
            return True
        time.sleep(0.3)
    return False


def slow_scroll_to_bottom(page, duration_ms: int, steps: int) -> None:
    step_delay_ms = max(50, duration_ms // steps)
    for _ in range(steps):
        try:
            page.evaluate(
                "(n) => window.scrollBy(0, Math.ceil(document.body.scrollHeight / n))",
                steps,
            )
        except PlaywrightError:
            break
        page.wait_for_timeout(step_delay_ms)


def fetch_state(context, base_url: str) -> dict:
    try:
        resp = context.request.get(f"{base_url}/api/state")
        if resp.ok:
            return resp.json()
        print(f"warning: GET /api/state returned {resp.status}", file=sys.stderr)
    except PlaywrightError as e:
        print(f"warning: could not fetch /api/state: {e}", file=sys.stderr)
    return {}


def main() -> int:
    base_url = env("LASTWORDS_URL").rstrip("/")
    if not base_url:
        print("error: LASTWORDS_URL is required", file=sys.stderr)
        return 1

    capture_dir = Path(env("CAPTURE_DIR", "./captures"))
    capture_message = env("CAPTURE_MESSAGE").strip()

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_dir = capture_dir / today
    out_dir.mkdir(parents=True, exist_ok=True)

    video_tmp_dir = out_dir / "_video_tmp"
    video_tmp_dir.mkdir(exist_ok=True)

    print(f"capturing {base_url} -> {out_dir}")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            viewport=VIEWPORT,
            record_video_dir=str(video_tmp_dir),
            record_video_size=VIEWPORT,
        )
        page = context.new_page()

        pre_state = fetch_state(context, base_url)
        silenced = bool(pre_state.get("silenced"))
        if silenced:
            print("the being is already silenced — recording the final poem instead of a conversation")

        page.goto(base_url, wait_until="load")

        if silenced:
            # The client's own JS checks /api/state on load and reveals the
            # poem block itself — just give it a moment to do that.
            wait_for_class_removed(page, "#silence-block", "hidden", max_wait_s=8)
            page.wait_for_timeout(1500)
        else:
            wait_for_ai_message(
                page,
                prev_count=0,
                max_wait_s=INITIAL_REPLAY_MAX_WAIT_S,
            )

            if capture_message:
                try:
                    prev_count = page.locator(".msg.ai .msg-line").count()
                    first_sacrifice = page.locator(".sacrifice-option").first
                    first_sacrifice.wait_for(state="visible", timeout=8000)
                    first_sacrifice.click()
                    page.fill("#message-input", capture_message)
                    page.click("#send-button")
                    wait_for_ai_message(page, prev_count=prev_count, max_wait_s=REPLY_MAX_WAIT_S)
                except PlaywrightError as e:
                    print(f"warning: scripted message failed: {e}", file=sys.stderr)

            page.wait_for_timeout(POST_REPLY_PAUSE_MS)

        main_png = out_dir / "main.png"
        page.screenshot(path=str(main_png))

        page.goto(f"{base_url}/remains", wait_until="load")
        page.wait_for_timeout(REMAINS_RENDER_WAIT_MS)
        slow_scroll_to_bottom(page, SCROLL_DURATION_MS, SCROLL_STEPS)

        remains_png = out_dir / "remains.png"
        page.screenshot(path=str(remains_png), full_page=True)

        post_state = fetch_state(context, base_url) or pre_state

        context.close()
        video_path = None
        try:
            if page.video:
                video_path = page.video.path()
        except PlaywrightError as e:
            print(f"warning: could not resolve recorded video path: {e}", file=sys.stderr)
        browser.close()

    final_video = out_dir / "capture.webm"
    if video_path and Path(video_path).exists():
        Path(video_path).replace(final_video)
    else:
        print("warning: no video was recorded", file=sys.stderr)

    # video_tmp_dir should be empty now; clean it up quietly if so.
    try:
        next(video_tmp_dir.iterdir())
    except StopIteration:
        video_tmp_dir.rmdir()
    except FileNotFoundError:
        pass

    state_out = {
        "date": today,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "url": base_url,
        "alive": post_state.get("alive"),
        "total": post_state.get("total"),
        "message_count": post_state.get("message_count"),
        "silenced": bool(post_state.get("silenced", False)),
    }
    (out_dir / "state.json").write_text(json.dumps(state_out, indent=2) + "\n")

    print(f"capture complete: {out_dir}")
    print(json.dumps(state_out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
