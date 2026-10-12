#!/usr/bin/env python3
"""Render the running interface in a real browser and check what it actually shows.

Every other check in this repository reads source, HTTP responses or the built
bundle. None of them can show that React mounted, that the corpus loaded, or that
the panel a reviewer reads really contains the coverage and empty-state sentences
the code intends. This script closes that gap.

It drives the application through its own controls in lightpanda (a headless
browser whose `serve` subcommand exposes the Chrome DevTools Protocol), then:

  1. waits for the interface to finish loading its own data (no "Loading…" state
     left on screen),
  2. optionally clicks "Select all" and "Analyse corpus with Apertus" and waits for
     the run to finish — with `--analyse` this calls the configured provider and
     costs tokens on that provider's key. Without it, no inference is requested,
  3. checks the rendered text for the coverage lines, the judged-outcome sentence,
     the empty-state sentence when a completed run reported nothing, and the
     prototype warning,
  4. scans the live DOM and the rendered text for footer markers, using the
     repository's own marker list so this check and `make no-footer` cannot drift,
  5. writes screenshots and an evidence JSON.

Only the browser's own DOM is used: nothing is injected into the page's scripts and
no request is answered locally, so what is captured is what a reviewer would see.

Usage:
    python3 scripts/browser_check.py                       # render only, no inference
    python3 scripts/browser_check.py --analyse             # real provider run through the UI
    python3 scripts/browser_check.py --base-url http://127.0.0.1:8098

Exit codes:
    0  every check passed
    1  a check failed
    2  the environment cannot run the check (no lightpanda, no reachable server)
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx
import websockets

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from check_no_footer import MARKER_FRAGMENTS  # noqa: E402

#: Footer markers come from the repository's checker, plus the closing tag the
#: checker cannot see in rendered text.
FOOTER_MARKERS = tuple(fragment.lower() for fragment, _label in MARKER_FRAGMENTS) + ("</footer",)

#: Sentences the interface is required to render, matched case-insensitively. The
#: coverage notice is found by its title, not by a class name, so a new-interface
#: restyle does not silently turn this check into a vacuous pass.
JUDGED_SENTENCE = re.compile(r"\d+ compared pair\(s\) were judged:", re.IGNORECASE)
EMPTY_STATE_SENTENCE = "no potential inconsistency was reported for this run"
PROTOTYPE_WARNING = "requires human review"

SKIP_EXIT = 2

# -- rendered-state extraction ------------------------------------------------

_STATE_JS = """
(function () {
  function noticeByTitle(title) {
    var nodes = document.querySelectorAll('.notice');
    for (var i = 0; i < nodes.length; i++) {
      var heading = nodes[i].querySelector('.notice-title');
      if (heading && (heading.textContent || '').trim().indexOf(title) === 0) return nodes[i];
    }
    return null;
  }
  function itemsOf(node) {
    if (!node) return [];
    var out = [];
    var list = node.querySelectorAll('li');
    if (list.length > 0) {
      for (var i = 0; i < list.length; i++) out.push((list[i].textContent || '').trim());
      return out;
    }
    var body = node.querySelector('.notice-body');
    if (body) out.push((body.textContent || '').trim());
    return out;
  }
  function statusGrids() {
    var out = [];
    var grids = document.querySelectorAll('.status-grid');
    for (var g = 0; g < grids.length; g++) {
      var dts = grids[g].querySelectorAll('dt');
      var dds = grids[g].querySelectorAll('dd');
      var pairs = {};
      for (var i = 0; i < dts.length && i < dds.length; i++) {
        pairs[(dts[i].textContent || '').trim()] = (dds[i].textContent || '').trim();
      }
      out.push(pairs);
    }
    return out;
  }
  function mutedLines() {
    var out = [];
    var nodes = document.querySelectorAll('p.muted, p.muted.small');
    for (var i = 0; i < nodes.length; i++) out.push((nodes[i].textContent || '').trim());
    return out;
  }
  function buttonLabels() {
    var out = [];
    var nodes = document.querySelectorAll('button');
    for (var i = 0; i < nodes.length; i++) {
      out.push({
        text: (nodes[i].textContent || '').trim(),
        disabled: !!nodes[i].disabled
      });
    }
    return out;
  }
  function brandMark() {
    var img = document.querySelector('img.brand-mark');
    if (!img) return { present: false };
    return {
      present: true,
      src: img.currentSrc || img.src || img.getAttribute('src') || '',
      complete: !!img.complete,
      natural_width: typeof img.naturalWidth === 'number' ? img.naturalWidth : null,
      natural_height: typeof img.naturalHeight === 'number' ? img.naturalHeight : null
    };
  }
  function documentNames() {
    var out = [];
    var nodes = document.querySelectorAll('.document-list .document-name');
    for (var i = 0; i < nodes.length; i++) out.push((nodes[i].textContent || '').trim());
    return out;
  }
  var text = document.body.innerText || document.body.textContent || '';
  return JSON.stringify({
    ready: document.querySelector('#settings-heading') !== null,
    loading_config: text.indexOf('Loading configuration') !== -1,
    loading_corpus: text.indexOf('Loading corpus') !== -1,
    running: text.indexOf('Running analysis') !== -1,
    coverage: itemsOf(noticeByTitle('Candidate coverage')),
    failures: itemsOf(noticeByTitle('Recorded failures')),
    limitations: itemsOf(noticeByTitle('Run limitations')),
    grids: statusGrids(),
    muted: mutedLines(),
    buttons: buttonLabels(),
    documents: documentNames(),
    logo: brandMark(),
    text: text
  });
})()
"""

_CLICK_JS = """
(function (text) {
  var needle = String(text).toLowerCase();
  var nodes = document.querySelectorAll('button, a, [role="button"]');
  for (var i = 0; i < nodes.length; i++) {
    var label = (nodes[i].textContent || '').trim().toLowerCase();
    if (label === needle || label.indexOf(needle) !== -1) {
      nodes[i].click();
      return (nodes[i].textContent || '').trim();
    }
  }
  return '';
})(%s)
"""

def js_string(value: str) -> str:
    """A JS literal for a string, so the caller cannot inject script."""
    return json.dumps(value)


_STARTED = time.monotonic()


def note(message: str) -> None:
    """Progress on stderr, so a long check is visibly alive while it runs."""
    print(f"[ui-check] {time.monotonic() - _STARTED:6.1f}s  {message}", file=sys.stderr, flush=True)


class CheckFailed(RuntimeError):
    pass


class CDP:
    """The subset of the Chrome DevTools Protocol this check needs."""

    def __init__(self, url: str) -> None:
        self.url = url
        self._socket: Any = None
        self._reader: asyncio.Task | None = None
        self._counter = 0
        self._pending: dict[int, asyncio.Future] = {}

    async def connect(self) -> None:
        # The analysis response carries every finding and its passages, so the
        # default 1 MiB frame limit is not enough.
        self._socket = await websockets.connect(self.url, max_size=128 * 1024 * 1024)
        self._reader = asyncio.create_task(self._pump())

    async def _pump(self) -> None:
        async for raw in self._socket:
            message = json.loads(raw)
            if "id" in message and message["id"] in self._pending:
                future = self._pending.pop(message["id"])
                if not future.done():
                    future.set_result(message)

    async def send(self, method: str, params: dict | None = None, session: str | None = None) -> dict:
        self._counter += 1
        message: dict[str, Any] = {"id": self._counter, "method": method}
        if params:
            message["params"] = params
        if session:
            message["sessionId"] = session
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[self._counter] = future
        await self._socket.send(json.dumps(message))
        response = await asyncio.wait_for(future, timeout=180)
        if "error" in response:
            raise CheckFailed(f"{method} failed: {response['error']}")
        return response.get("result", {})

    async def close(self) -> None:
        if self._reader:
            self._reader.cancel()
        if self._socket:
            await self._socket.close()


def find_lightpanda(explicit: str | None) -> str | None:
    """The path to use, or None when no usable binary can be found.

    An explicit path is taken at its word: if it is not there, the check is skipped
    rather than quietly running some other lightpanda found on PATH, because the
    caller named the binary they wanted used.
    """
    if explicit:
        candidate = Path(explicit).expanduser()
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
        return None
    candidates = []
    from_path = shutil.which("lightpanda")
    if from_path:
        candidates.append(Path(from_path))
    candidates.append(Path("~/.local/bin/lightpanda").expanduser())
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def start_browser(binary: str, port: int, http_timeout_ms: int, connect_timeout_ms: int) -> subprocess.Popen:
    """Start the browser's CDP server with timeouts that suit a slow API.

    The browser's own HTTP timeouts default to 15 s (transfer) and 8 s (connect).
    Analysis is a synchronous endpoint that can take minutes and sends nothing
    while it works, so a browser left at the default aborts the request and the
    interface never renders the run. These two flags are why this check can read a
    real run at all; without them the POST fails and the page keeps its empty state.
    """
    process = subprocess.Popen(
        [
            binary,
            "serve",
            "--port",
            str(port),
            "--protocol",
            "cdp",
            "--http-timeout",
            str(http_timeout_ms),
            "--http-connect-timeout",
            str(connect_timeout_ms),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
    return process


def wait_for_browser(port: int, timeout: float = 20.0) -> dict:
    deadline = time.monotonic() + timeout
    last_error = ""
    while time.monotonic() < deadline:
        try:
            response = httpx.get(f"http://127.0.0.1:{port}/json/version", timeout=2.0)
            if response.status_code == 200:
                return response.json()
            last_error = f"HTTP {response.status_code}"
        except Exception as caught:  # the port is not open yet
            last_error = str(caught)
        time.sleep(0.25)
    raise CheckFailed(f"the browser's CDP endpoint on port {port} never answered: {last_error}")


def stop_browser(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
    except Exception:
        process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except Exception:
            process.kill()


async def evaluate(cdp: CDP, session: str, expression: str) -> Any:
    result = await cdp.send(
        "Runtime.evaluate",
        {"expression": expression, "returnByValue": True, "awaitPromise": True},
        session,
    )
    outcome = result.get("result", {})
    if outcome.get("subtype") == "error":
        raise CheckFailed(f"the page raised an error: {outcome.get('description')}")
    return outcome.get("value")


async def wait_for(
    cdp: CDP,
    session: str,
    expression: str,
    timeout: float,
    label: str,
    *,
    note_every: float = 0.0,
) -> Any:
    deadline = time.monotonic() + timeout
    started = time.monotonic()
    next_note = started + note_every if note_every else None
    last: Any = None
    while time.monotonic() < deadline:
        last = await evaluate(cdp, session, expression)
        if last:
            return last
        if next_note is not None and time.monotonic() >= next_note:
            note(f"still waiting for {label} ({time.monotonic() - started:.0f}s)")
            next_note = time.monotonic() + note_every
        await asyncio.sleep(0.5)
    raise CheckFailed(f"timed out after {timeout:.0f}s waiting for {label}")


async def read_state(cdp: CDP, session: str) -> dict:
    raw = await evaluate(cdp, session, _STATE_JS)
    return json.loads(raw)


async def screenshot(
    cdp: CDP,
    session: str,
    path: Path,
    *,
    width: int,
    height: int | None = None,
    capture_timeout: float = 120.0,
) -> int:
    """Capture the page, growing the viewport first so a long panel is not cut off.

    The browser has no page-bound capture of its own, so the viewport is enlarged
    before the shot and left that way afterwards; the check ends here.
    """
    if height:
        await cdp.send(
            "Emulation.setDeviceMetricsOverride",
            {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False},
            session,
        )
    try:
        result = await asyncio.wait_for(
            cdp.send("Page.captureScreenshot", {"format": "png"}, session),
            timeout=capture_timeout,
        )
    except asyncio.TimeoutError:
        raise CheckFailed(
            f"the browser did not return {path.name} within {capture_timeout:.0f}s"
        ) from None
    data = result.get("data") or ""
    if not data:
        raise CheckFailed(f"the browser returned no screenshot data for {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = base64.b64decode(data)
    path.write_bytes(raw)
    return len(raw)


def footer_hits(text: str) -> list[str]:
    lowered = text.lower()
    return sorted({marker for marker in FOOTER_MARKERS if marker in lowered})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://127.0.0.1:8098", help="origin of the running application")
    parser.add_argument("--cdp-port", type=int, default=9222, help="port for the browser's CDP server")
    parser.add_argument("--lightpanda", default=None, help="path to the lightpanda binary")
    parser.add_argument("--analyse", action="store_true", help="run a real provider analysis through the UI")
    parser.add_argument("--timeout", type=float, default=180.0, help="seconds to wait for the interface to load")
    parser.add_argument("--analysis-timeout", type=float, default=900.0, help="seconds to wait for a run")
    parser.add_argument("--viewport-width", type=int, default=1500, help="capture width in pixels")
    parser.add_argument(
        "--capture-height",
        type=int,
        default=3000,
        help="capture height in pixels; the page is not measurable in this browser",
    )
    parser.add_argument(
        "--screenshot-timeout", type=float, default=120.0, help="seconds to wait for one capture"
    )
    parser.add_argument(
        "--http-timeout-ms",
        type=int,
        default=900_000,
        help="the browser's transfer timeout; the default of 15000 aborts a slow analysis",
    )
    parser.add_argument(
        "--connect-timeout-ms", type=int, default=30_000, help="the browser's connect timeout"
    )
    parser.add_argument(
        "--screenshot-dir",
        default=str(REPO_ROOT / "docs" / "demo" / "screenshots"),
        help="where to write screenshots",
    )
    parser.add_argument(
        "--evidence-out",
        default=str(REPO_ROOT / "track_2b" / "data" / "evaluation" / "UI_RENDER.json"),
        help="where to write the evidence JSON",
    )
    return parser


async def run(args: argparse.Namespace, bucket: dict) -> dict:
    binary = find_lightpanda(args.lightpanda)
    if binary is None:
        reason = (
            f"--lightpanda {args.lightpanda} is not an executable file"
            if args.lightpanda
            else "lightpanda was not found on PATH or at ~/.local/bin/lightpanda"
        )
        raise SystemExit(
            f"[ui-check] SKIPPED: {reason}.\n"
            "           Everything else in this repository is checked without a browser;"
            " this is the\n           one check that needs one. Install lightpanda, or pass"
            " --lightpanda /path/to/lightpanda."
        )

    try:
        httpx.get(f"{args.base_url}/health", timeout=5.0)
    except Exception as caught:
        raise SystemExit(
            f"[ui-check] SKIPPED: no application is answering at {args.base_url} ({caught}).\n"
            "           Start it first: make run-local   (or make run for Docker)"
        )

    process = start_browser(binary, args.cdp_port, args.http_timeout_ms, args.connect_timeout_ms)
    note(f"starting {binary} on port {args.cdp_port}")
    # The caller's dict *is* the evidence, so a failed check still leaves behind what
    # the browser had rendered when it failed instead of only an exit code.
    bucket.clear()
    evidence: dict[str, Any] = bucket
    evidence.update({"base_url": args.base_url, "browser": None, "screenshots": []})
    try:
        version = wait_for_browser(args.cdp_port)
        note(f"browser ready: {version.get('Lightpanda-Version')}")
        evidence["browser"] = {
            "product": version.get("Browser"),
            "version": version.get("Lightpanda-Version"),
            "binary": binary,
            "http_timeout_ms": args.http_timeout_ms,
            "connect_timeout_ms": args.connect_timeout_ms,
        }
        cdp = CDP(version["webSocketDebuggerUrl"])
        await cdp.connect()
        try:
            created = await cdp.send("Target.createTarget", {"url": "about:blank"})
            attached = await cdp.send(
                "Target.attachToTarget", {"targetId": created["targetId"], "flatten": True}
            )
            session = attached["sessionId"]
            await cdp.send("Page.enable", {}, session)

            started = time.monotonic()
            note(f"loading {args.base_url.rstrip('/')}/app/")
            await cdp.send("Page.navigate", {"url": f"{args.base_url.rstrip('/')}/app/"}, session)
            # The interface loads three endpoints on mount; wait until none of the
            # panels still shows a loading state and the corpus controls exist.
            await wait_for(
                cdp,
                session,
                "!document.body.textContent.includes('Loading configuration') && "
                "!!document.querySelector('#corpus-heading')",
                args.timeout,
                "the interface to finish loading its own data",
            )
            state = await read_state(cdp, session)
            evidence["load_seconds"] = round(time.monotonic() - started, 2)
            note(
                f"interface loaded in {evidence['load_seconds']}s with "
                f"{len(state['documents'])} document(s)"
            )

            title = await evaluate(cdp, session, "document.title")
            assert_permanent_contract(state, title)
            evidence["logo"] = check_logo(state, args.base_url)
            note(f"header mark served: {evidence['logo']['src']}")
            evidence["documents"] = state["documents"]
            evidence["settings"] = grid_with(state, "Provider reachability")
            evidence["usage"] = grid_with(state, "Provider calls")
            inference_ready = "primary provider reachable" in state["text"].lower()
            evidence["provider_reachable"] = inference_ready
            evidence["analyse_button"] = next(
                (
                    {
                        "text": button["text"],
                        "disabled_before_selection": button["disabled"],
                    }
                    for button in state["buttons"]
                    if "analyse corpus" in button["text"].lower()
                ),
                None,
            )
            if evidence["analyse_button"] is None:
                raise CheckFailed("the analysis control is not on the page at all")
            if args.analyse and not inference_ready:
                raise CheckFailed(
                    "the provider is not reachable from the page, so a run cannot be read: "
                    f"{state['settings'].get('Provider reachability')!r}"
                )
            # The before shot uses the same viewport as the after shot, so the two
            # images can be compared directly and the run is visibly the difference.
            corpus_shot = Path(args.screenshot_dir) / "01-corpus.png"
            evidence["screenshots"].append(
                {
                    "path": str(relative(corpus_shot)),
                    "bytes": await screenshot(
                        cdp,
                        session,
                        corpus_shot,
                        width=args.viewport_width,
                        height=args.capture_height,
                        capture_timeout=args.screenshot_timeout,
                    ),
                    "state": (
                        f"corpus loaded and nothing analysed yet, at "
                        f"{args.viewport_width}x{args.capture_height}"
                    ),
                }
            )
            note(f"captured {relative(corpus_shot)}")

            if args.analyse:
                evidence.update(await drive_analysis(cdp, session, args, state, evidence["screenshots"]))

            final = await read_state(cdp, session)
            evidence["rendered"] = {
                "run": grid_with(final, "Run status"),
                "coverage": final["coverage"],
                "failures": final["failures"],
                "limitations": final["limitations"],
                "buttons": [button["text"] for button in final["buttons"] if button["text"]],
            }
            try:
                evidence["rendered_checks"] = check_rendered_text(final)
                note("rendered text satisfies the coverage contract")
                evidence["footer_scan"] = await footer_scan(final, cdp, session)
                note("live DOM and rendered text scanned for footer markers")
            except CheckFailed as failure:
                # Keep the text that produced the failure, so a failing run is
                # diagnosable without re-running it.
                evidence["error"] = str(failure)
                evidence["diagnostic_text"] = final["text"][:6000]
                raise
            if evidence["footer_scan"]["markers"]:
                raise CheckFailed(
                    "footer markers are present in the live page: "
                    + ", ".join(evidence["footer_scan"]["markers"])
                )
            evidence["notes"] = [
                "The page is rendered by a real browser; nothing is stubbed, so what the "
                "evidence describes is what a reviewer sees.",
                "The application answers a repeated analysis of the same document set from its "
                "own stored run, so the round trip can be short. The usage summary is the "
                "displayed run's record of provider calls, tokens and accumulated latency.",
                "Screenshots are pixels, not assertions: the assertions are the rendered-text "
                "checks and the footer scan above.",
            ]
            return evidence
        finally:
            await cdp.close()
    finally:
        stop_browser(process)


async def drive_analysis(
    cdp: CDP, session: str, args: argparse.Namespace, initial: dict, screenshots: list[dict]
) -> dict:
    """Click the corpus controls a reviewer clicks, then wait for the run."""
    result: dict[str, Any] = {}
    clicked = await evaluate(cdp, session, _CLICK_JS % js_string("Select all"))
    if not clicked:
        raise CheckFailed("no 'Select all' control was found on the page")
    total = len(initial["documents"])
    if total < 2:
        raise CheckFailed(f"the corpus holds {total} document(s); a comparison needs at least two")
    await wait_for(
        cdp,
        session,
        f"document.body.textContent.includes('{total} of {total} selected')",
        args.timeout,
        "every document to be selected",
    )
    result["selected"] = f"{total} of {total}"
    note(f"{total} of {total} documents selected through the interface")

    enabled = await wait_for(
        cdp,
        session,
        "(function(){var b=document.querySelectorAll('button');"
        "for(var i=0;i<b.length;i++){if((b[i].textContent||'').toLowerCase().indexOf('analyse corpus')!==-1)"
        "{return !b[i].disabled;}}return false;})()",
        30.0,
        "the analysis control to become available once the corpus is selected",
    )
    result["control_enabled_after_selection"] = bool(enabled)

    started = time.monotonic()
    note("clicking 'Analyse corpus with Apertus'")
    launched = await evaluate(cdp, session, _CLICK_JS % js_string("Analyse corpus"))
    if not launched:
        raise CheckFailed("the analysis control could not be clicked")
    result["clicked"] = launched
    await wait_for(
        cdp,
        session,
        "document.body.textContent.includes('Running analysis')",
        60.0,
        "the run to be reported as running",
    )
    await wait_for(
        cdp,
        session,
        "!document.body.textContent.includes('Running analysis') && "
        "!document.body.textContent.includes('No analysis has run in this session')",
        args.analysis_timeout,
        "the analysis to finish",
        note_every=30.0,
    )
    result["analysis_round_trip_seconds"] = round(time.monotonic() - started, 2)
    note(f"run finished: {result['analysis_round_trip_seconds']}s round trip")

    state = await read_state(cdp, session)
    result["run"] = grid_with(state, "Run status")
    result["usage"] = grid_with(state, "Provider calls")

    # The post-run shot is taken from a tall viewport so the finding list, the run
    # summary and the coverage notice are all in one image.
    # A fixed, generous viewport. This browser reports 100000000 for every
    # ``scrollHeight`` and offsetHeight, so measuring the document and capturing
    # exactly it is not possible; a tall viewport shows the panel in one image.
    note(f"capturing the page at {args.viewport_width}x{args.capture_height}")
    findings_shot = Path(args.screenshot_dir) / "02-findings.png"
    screenshots.append(
        {
            "path": str(relative(findings_shot)),
            "bytes": await screenshot(
                cdp,
                session,
                findings_shot,
                width=args.viewport_width,
                height=args.capture_height,
                capture_timeout=args.screenshot_timeout,
            ),
            "state": (
                f"after the run: the findings panel, the run summary and the coverage "
                f"notice at {args.viewport_width}x{args.capture_height}"
            ),
        }
    )
    if state["failures"]:
        result["recorded_failures"] = state["failures"]
    return result


def check_logo(state: dict, base_url: str, fetch: Any = None) -> dict:
    """The header mark must be an image URL the server actually serves.

    A broken image is silent on a page: the layout keeps the box, the header looks
    finished, and nothing is reported. The dashboard shipped exactly that — the
    build is mounted at /app while the component asked for /sovra-logo.png, so the
    header pointed at a 404. This check fetches the URL the page itself resolved.
    """
    mark = state.get("logo") or {}
    if not mark.get("present"):
        raise CheckFailed("the header has no brand mark element at all")
    src = mark.get("src") or ""
    if not src:
        raise CheckFailed("the brand mark has no resolved image URL")
    url = src if src.startswith("http") else urljoin(base_url, src)
    fetch = fetch or (lambda target: httpx.get(target, timeout=10.0))
    try:
        response = fetch(url)
    except Exception as caught:
        raise CheckFailed(f"the brand mark URL {src} could not be fetched: {caught}") from None
    content_type = response.headers.get("content-type", "")
    if response.status_code != 200 or not content_type.startswith("image/"):
        raise CheckFailed(
            f"the header asks for {src}, which the server answers with HTTP "
            f"{response.status_code} {content_type or '(no content type)'}"
        )
    width = mark.get("natural_width")
    return {
        "src": src,
        "status": response.status_code,
        "content_type": content_type,
        "bytes": len(response.content),
        # Recorded, never asserted: this browser answers 0 for every image's
        # naturalWidth because its layout metrics are stubs, so a non-zero value
        # here would be the surprise, not a pass.
        "decoded_width_reported": width,
        "assertion": (
            "the URL the page resolved for the header mark is served as an image "
            "(HTTP status and content type); decode metrics are not usable in this browser"
        ),
    }


def grid_with(state: dict, label: str) -> dict:
    """The status grid carrying a given label, or {} when no grid does.

    The page renders three of these — provider settings, the run summary and the
    usage counters — so they are found by a label they own rather than by order.
    """
    for grid in state.get("grids") or []:
        if label in grid:
            return grid
    return {}


def assert_permanent_contract(state: dict, title: str) -> None:
    """Things that must hold before any run: the page is the app, and it warns."""
    if "Sovra Verify" not in (title or ""):
        raise CheckFailed(f"the page at /app/ is not the application (title: {title!r})")
    if PROTOTYPE_WARNING not in state["text"].lower():
        raise CheckFailed("the prototype warning is not rendered anywhere near the controls")
    if not state["ready"]:
        raise CheckFailed("the configuration panel never rendered")


def check_rendered_text(state: dict) -> dict:
    """The coverage contract, read off the screen rather than off the source.

    Without a run there is nothing to compare, so the check states that plainly
    instead of passing a coverage contract that was never exercised.
    """
    run_grid = grid_with(state, "Run status")
    checks: dict[str, Any] = {"run_rendered": bool(run_grid)}
    if not checks["run_rendered"]:
        if "No analysis has run in this session" not in state["text"]:
            raise CheckFailed(
                "no run has been rendered, but the interface does not say so either"
            )
        checks["coverage_notice"] = "not applicable: no run has been rendered yet"
        return checks

    if not state["coverage"]:
        raise CheckFailed("a run is on screen but the 'Candidate coverage' notice is not rendered")
    checks["coverage_notice"] = state["coverage"]

    pairs_compared = (run_grid.get("Pairs compared") or "").strip()
    if pairs_compared not in ("", "0"):
        joined = " ".join(state["coverage"])
        if not JUDGED_SENTENCE.search(joined):
            raise CheckFailed(
                "pairs were compared but the coverage notice never states how they were "
                f"judged: {state['coverage']}"
            )
        checks["judged_outcome_sentence"] = True

    findings_line = next(
        (line for line in state["muted"] if line.lower().startswith("showing ")), ""
    )
    if findings_line.startswith("Showing 0 of 0"):
        if not any(line.lower().startswith(EMPTY_STATE_SENTENCE) for line in state["muted"]):
            raise CheckFailed(
                "a completed run with no findings does not state that nothing was reported"
            )
        checks["empty_state_sentence"] = True
    return checks


async def footer_scan(state: dict, cdp: CDP, session: str) -> dict:
    """Scan the live page: the text a reader sees, and the DOM that produced it.

    Both are checked because a footer can be present in markup while hidden, and a
    marker can be visible in text that no attribute reveals. The DOM string is not
    kept in the evidence file; only the verdict and the counts are.
    """
    html = await evaluate(cdp, session, "document.documentElement.outerHTML")
    text_hits = footer_hits(state["text"])
    dom_hits = footer_hits(html or "")
    return {
        "markers": sorted(set(text_hits) | set(dom_hits)),
        "text_markers": text_hits,
        "dom_markers": dom_hits,
        "rendered_characters": len(state["text"]),
        "dom_characters": len(html or ""),
    }


def relative(path: Path) -> Path:
    try:
        return path.resolve().relative_to(REPO_ROOT)
    except ValueError:
        return path


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    bucket: dict[str, Any] = {}
    failure_text = None
    try:
        evidence = asyncio.run(run(args, bucket))
    except SystemExit as skipped:
        print(skipped.code)
        return SKIP_EXIT
    except CheckFailed as failure:
        failure_text = str(failure)
        evidence = bucket
        evidence["error"] = failure_text

    if args.evidence_out and evidence:
        out = Path(args.evidence_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if failure_text:
        print(f"[ui-check] FAIL: {failure_text}")
        return 1

    print("[ui-check] PASS: the interface rendered and every required sentence is on screen")
    print(f"  browser          : {evidence['browser']['product']} {evidence['browser']['version']}")
    print(f"  documents offered: {len(evidence['documents'])} ({', '.join(evidence['documents'])})")
    if "analysis_round_trip_seconds" in evidence:
        print(f"  selected         : {evidence['selected']}")
        print(f"  analysis         : {evidence['analysis_round_trip_seconds']}s round trip through the interface")
        usage = evidence.get("usage") or {}
        if usage:
            print(
                "  provider usage   : "
                f"{usage.get('Provider calls', '?')} calls · "
                f"{usage.get('Total tokens', '?')} tokens · "
                f"{usage.get('Accumulated latency', '?')} latency · "
                f"{usage.get('Failed calls', '?')} failed"
            )
        run_summary = evidence.get("run") or {}
        if run_summary:
            print(
                "  run summary      : "
                f"{run_summary.get('Run status', '?')} · "
                f"{run_summary.get('Mode', '?')} · "
                f"prompt {run_summary.get('Prompt version', '?')} · "
                f"claims {run_summary.get('Validated claims', '?')} · "
                f"pairs {run_summary.get('Pairs compared', '?')}"
            )
    checks = evidence["rendered_checks"]
    if not checks.get("run_rendered"):
        print("  coverage contract: not exercised — no run was rendered (re-run with --analyse)")
    print(f"  coverage lines   : {len(evidence['rendered']['coverage'])}")
    for line in evidence["rendered"]["coverage"]:
        print(f"    - {line}")
    run_summary = evidence["rendered"].get("run") or {}
    if run_summary.get("Pairs compared") is not None:
        print(f"  pairs compared   : {run_summary['Pairs compared']}")
    for name in ("judged_outcome_sentence", "empty_state_sentence"):
        if checks.get(name):
            print(f"  rendered check   : {name} present")
    print(
        f"  footer scan      : no markers in {evidence['footer_scan']['rendered_characters']} "
        f"rendered characters or {evidence['footer_scan']['dom_characters']} DOM characters"
    )
    for shot in evidence["screenshots"]:
        print(f"  screenshot       : {shot['path']} ({shot['bytes']} bytes, {shot['state']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
