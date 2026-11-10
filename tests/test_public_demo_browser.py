"""Opt-in real Chromium checks; set CITEPROBE_BROWSER to Chrome/Edge's executable."""

import json
import os
import subprocess
import sys
import time
from collections.abc import Iterator
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.request import urlopen

import pytest


class StaticHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass

    def do_GET(self) -> None:
        if self.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
        else:
            super().do_GET()


@pytest.fixture(scope="module")
def browser_target(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[str, str, Path]]:
    executable = os.environ.get("CITEPROBE_BROWSER")
    if not executable:
        pytest.skip("Set CITEPROBE_BROWSER to run the real-browser release checks")
    profile = tmp_path_factory.mktemp("chromium")
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(StaticHandler, directory=str(Path("public-demo").resolve()))
    )
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    process = subprocess.Popen(
        [
            executable,
            "--headless",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-networking",
            "--remote-debugging-address=127.0.0.1",
            "--remote-debugging-port=0",
            f"--user-data-dir={profile}",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    try:
        port_file = profile / "DevToolsActivePort"
        deadline = time.monotonic() + 15
        while not port_file.exists():
            if process.poll() is not None or time.monotonic() > deadline:
                pytest.fail("Headless browser did not start")
            time.sleep(0.05)
        port = int(port_file.read_text().splitlines()[0])
        with urlopen(f"http://127.0.0.1:{port}/json/list", timeout=5) as response:
            targets = json.load(response)
        target = next(t for t in targets if t["type"] == "page")["webSocketDebuggerUrl"]
        yield target, f"http://127.0.0.1:{server.server_port}", profile.parent
    finally:
        process.terminate()
        process.wait(timeout=10)
        server.shutdown()
        worker.join(timeout=5)
        server.server_close()


@pytest.mark.parametrize("width", [320, 390, 768, 1440])
def test_public_demo_in_chromium(browser_target: tuple[str, str, Path], width: int) -> None:
    target, origin, output = browser_target
    result = subprocess.run(
        [
            "node",
            "tests/public_demo_browser.cjs",
            target,
            origin,
            str(width),
            str(output),
            sys.executable,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["width"] == width
    assert report["papers"] == 8
    assert report["candidates"] == 41
    assert report["errors"] == []
