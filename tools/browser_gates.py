#!/usr/bin/env python3
"""Open the browser page and hold it to what it says about itself.

    python tools/build_browser.py          # dist/aas-submodel-validate.html
    python tools/browser_gates.py          # open it, judge everything here, count

The page says it judges a submodel in the browser, installing nothing and
sending the file nowhere, and that its report is the one the command line
gives. A browser can be made to answer each of those by counting, so this
counts.

* **Nothing is sent.** Every request is counted four ways: by the browser's
  own network events, which see the page and the worker it starts; by the
  server that hands the page out; and by the Resource Timing of the page and
  of the worker, each read from the inside. The count runs from the moment
  the page says it is ready to the moment the last file has been judged, and
  it has to be zero. A counter attached to the wrong thing reads zero as
  well, so the page and the worker are then each made to fetch once and
  every counter has to see it. And three files are built for the run that
  ask the reader to reach out to that same server -- an external entity, a
  schema location and a relationship whose target is the server -- so the
  door is opened rather than assumed shut.
* **Nothing is fetched to start it.** While it loads, the page asks for
  nothing but itself: the runtime, the reader and the rules travel inside
  the file.
* **Nothing is installed.** No cookie and no local storage, and on the page
  served no cache and no service worker; no download it did not ask for.
  A page opened from a disk is asked for cookies only, and IndexedDB and
  the origin's private file system are not read: that the page keeps
  nothing there is its source's to show, and it calls no storage at all.
* **The report is the command's.** Every file the release notes measure and
  every official sample here is judged by the page and by the command, with
  the same arguments, as text and as JSON, and stdout, stderr and the exit
  code are compared as bytes. Then the same file is opened from a disk, the
  way a downloaded copy is, and asked all of it again.

Exit 0 when all of it holds, 1 when any of it does not, and 2 when it cannot
be asked: no page, no browser, or a command running on another Python from
the page's -- where a difference could not be told apart from the way in it
came through.
"""
from __future__ import annotations

import argparse
import base64
import concurrent.futures
import functools
import http.server
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from collections import namedtuple
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:                     # said below, with what to install
    sync_playwright = None

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "dist" / "aas-submodel-validate.html"
SAMPLES = ROOT / "tests" / "corpus" / "idta"

#: The Playwright this was written against, and the one CI installs.
PLAYWRIGHT = "1.63.0"

#: The command, from this tree, at a UTF-8 console -- the console the page
#: stands for. Spelled out rather than inherited, so that what the comparison
#: runs does not depend on the locale of whichever machine runs it.
COMMAND_ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8",
                   PYTHONPATH=str(ROOT / "src"))

# The tree's own source first, as every tool here puts it: the job that runs
# this installs the one dependency and not this project, and the corpus is
# built by this tree's engine.
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "src"))
import verdict_diff  # noqa: E402 -- the corpus the release notes measure
from builders import build_aasx, hd_env  # noqa: E402


def _the_pages_python():
    """`browser/aas_page.py`, which decides what the page runs.

    Loaded from its file rather than imported by name: it is the page's code
    and lives with the page, and the arguments it builds are the ones this
    compares against -- read from there, not copied here."""
    spec = importlib.util.spec_from_file_location("aas_page", ROOT / "browser" / "aas_page.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


Run = namedtuple("Run", "argv stdout stderr code")


def official_samples() -> list:
    """Every official IDTA file this repository carries for its tests."""
    return sorted(path for path in SAMPLES.rglob("*") if path.suffix in (".aasx", ".json", ".xml"))


def inputs(into: Path) -> list:
    """What the page and the command are both asked about: every case in the
    corpus the release notes measure that is a file -- a path with nothing
    behind it cannot be handed to a page -- then the official samples, each
    once."""
    into.mkdir(parents=True, exist_ok=True)
    corpus = [Path(case.path) for case in verdict_diff.build_corpus(into)]
    return list(dict.fromkeys([path for path in corpus if path.is_file()] + official_samples()))


def differences(page: Run, cli: Run) -> list:
    """What differs between two runs of one command, stream by stream."""
    if list(page.argv) != list(cli.argv):
        return ["argv: the page ran %s and the command %s, so their outputs say "
                "nothing about each other" % (page.argv, cli.argv)]
    said = []
    for stream in ("stdout", "stderr"):
        mine, theirs = getattr(page, stream), getattr(cli, stream)
        if mine != theirs:
            said.append("%s: %s" % (stream, _where(mine, theirs)))
    if page.code != cli.code:
        said.append("exit code: the page %s, the command %s" % (page.code, cli.code))
    return said


def _where(mine: bytes, theirs: bytes) -> str:
    at = next((n for n, (a, b) in enumerate(zip(mine, theirs)) if a != b),
              min(len(mine), len(theirs)))
    return ("%d bytes from the page, %d from the command, first different at byte %d: "
            "page %r, command %r" % (len(mine), len(theirs), at,
                                     mine[max(0, at - 30):at + 50], theirs[max(0, at - 30):at + 50]))


def blind(expected: dict, seen: dict) -> list:
    """The counters that did not see the requests they were shown.

    A zero from one of these says nothing: it is the reading a counter gives
    when it is attached to the wrong thing."""
    return [name for name, want in expected.items() if seen.get(name, 0) < want]


def unlike(page: dict, here: dict) -> list:
    """What decides a verdict and differs between the page's runtime and the
    command's: the Python, to the patch release, and each package, exactly.
    A patch release can change what the standard library accepts -- its
    `zipfile` and its XML parser are this reader's first words on a file --
    so two patches of one minor version are two readers."""
    return [name for name in ("python", "aas_submodel_validate", "aas_core3")
            if page.get(name) != here.get(name)]


def command(argv, cwd) -> Run:
    done = subprocess.run([sys.executable, "-m", "aas_submodel_validate", *argv],
                          cwd=str(cwd), capture_output=True, timeout=600, env=COMMAND_ENV)
    return Run(list(argv), done.stdout, done.stderr, done.returncode)


def versions_here() -> dict:
    done = subprocess.run(
        [sys.executable, "-c",
         "import json, sys; sys.path.insert(0, sys.argv[1]); import aas_page; "
         "print(json.dumps(aas_page.versions()))", str(ROOT / "browser")],
        capture_output=True, text=True, timeout=120, env=COMMAND_ENV)
    if done.returncode:
        raise SystemExit("could not ask this Python what it would run:\n%s" % done.stderr)
    return json.loads(done.stdout)


class Server:
    """Hands out the page, and writes down every request anybody makes of it."""

    def __init__(self, page: Path):
        self.page, self.seen, self._lock = page, [], threading.Lock()
        handler = functools.partial(_Handler, self)
        self._httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.base = "http://127.0.0.1:%d/" % self._httpd.server_address[1]
        threading.Thread(target=self._httpd.serve_forever, daemon=True).start()

    def saw(self, path, agent):
        with self._lock:
            self.seen.append((path, agent))

    def count(self):
        with self._lock:
            return len(self.seen)

    def since(self, mark):
        with self._lock:
            return self.seen[mark:]

    def close(self):
        self._httpd.shutdown()
        self._httpd.server_close()


class _Handler(http.server.BaseHTTPRequestHandler):
    def __init__(self, server_record, *args, **kwargs):
        self.record = server_record
        super().__init__(*args, **kwargs)

    def do_GET(self):                         # the name http.server calls
        self.record.saw(self.path, self.headers.get("User-Agent", ""))
        if self.path == "/" + self.record.page.name and self.record.page.is_file():
            body = self.record.page.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()

    do_POST = do_HEAD = do_GET

    def log_message(self, *args):
        pass


#: The three files `doors` makes, by name, so the run can be asked whether
#: they were in it.
DOORS = ("door-external-entity.xml", "door-schema-location.xml",
         "door-external-relationship.aasx")


def doors(into: Path, base: str) -> list:
    """Three files that ask the reader to reach the server this run started.

    Two are an AAS environment written as XML with one change: one declares
    an external entity at the server and uses it, the other points its
    schema location there. The third is a package whose specification part
    declares a supplementary file by a relationship whose target is the
    server. A reader that followed any of them would make a request the
    server writes down, while the page is being counted."""
    from aas_core3 import jsonization, xmlization

    into.mkdir(parents=True, exist_ok=True)
    environment = hd_env()
    xml = xmlization.to_str(jsonization.environment_from_jsonable(environment))
    declaration = '<?xml version="1.0" encoding="UTF-8"?>\n'
    first = xml.index("<value>") + len("<value>")
    entity = (declaration
              + '<!DOCTYPE environment [<!ENTITY pull SYSTEM "%sdoor/entity">]>\n' % base
              + xml[:first] + "&pull;" + xml[xml.index("</value>", first):])
    root = xml.index("<environment") + len("<environment")
    schema = (declaration + xml[:root]
              + ' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
                ' xsi:schemaLocation="https://admin-shell.io/aas/3/0 %sdoor/schema.xsd"' % base
              + xml[root:])
    made = []
    for name, text in zip(DOORS[:2], (entity, schema)):
        if base not in text or text == xml:
            raise SystemExit("%s: the environment no longer has the text this door is made "
                             "by changing, so the door would be shut" % name)
        target = into / name
        target.write_text(text, encoding="utf-8")
        made.append(target)
    package = into / DOORS[2]
    build_aasx(package, payload=json.dumps(environment).encode("utf-8"),
               suppl_external=(base + "door/relationship",))
    made.append(package)
    return made


#: Two documents nested far past the reader's bound -- one JSON, one XML --
#: and deep enough that the runtime's stack runs out on them before a
#: parser's own limit would: before the bound, the page crashed on both
#: where the command reported. Named, so the run can be asked whether they
#: were in it.
DEEP = ("deep-3000.json", "deep-3000.xml")


def deep(into: Path) -> list:
    into.mkdir(parents=True, exist_ok=True)
    nested = into / DEEP[0]
    nested.write_bytes(b"[" * 3000 + b"]" * 3000)
    elements = into / DEEP[1]
    elements.write_bytes(b'<environment xmlns="https://admin-shell.io/aas/3/0">'
                         + b"<a>" * 2999 + b"</a>" * 2999 + b"</environment>")
    return [nested, elements]


#: Read a run out of the page as base64, so the bytes cross unchanged.
READ_RUNS = """(k) => {
  const b64 = (u8) => { let s = "";
    for (let i = 0; i < u8.length; i += 0x8000) s += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000));
    return btoa(s); };
  return window.smtv.runs.slice(k).map(r => ({argv: r.argv, code: r.code,
    stdout: b64(r.stdout), stderr: b64(r.stderr)}));
}"""

TIMING = "performance.getEntriesByType('resource').map(e => e.name)"


def page_runs(page, path: Path) -> list:
    """Hand the page one file through its own file input, as a person does,
    and read back the two runs it made of it -- text, then JSON."""
    k = page.evaluate("window.smtv.runs.length")
    page.set_input_files("#file", str(path))
    page.wait_for_function(
        "window.smtv.failed || (window.smtv.runs.length >= %d && !window.smtv.busy)" % (k + 2),
        timeout=600_000)
    failed = page.evaluate("window.smtv.failed")
    if failed:
        raise SystemExit("the page failed on %s: %s" % (path.name, failed))
    return [Run(r["argv"], base64.b64decode(r["stdout"]), base64.b64decode(r["stderr"]), r["code"])
            for r in page.evaluate(READ_RUNS, k)]


class Watched:
    """One open page, with every counter attached before it loads."""

    def __init__(self, context, url, server):
        self.url, self.server, self.requests, self.downloads, self.console = url, server, [], [], []
        context.on("request", lambda r: self.requests.append(r.url))
        self.page = context.new_page()
        self.page.on("download", lambda d: self.downloads.append(d))
        self.page.on("console", lambda m: self.console.append(m.text))
        self.page.on("pageerror", lambda e: self.console.append("page error: %s" % e))
        started = time.monotonic()
        self.page.goto(url)
        try:
            self.page.wait_for_function(
                "window.smtv && (window.smtv.ready || window.smtv.failed)", timeout=180_000)
        except Exception as e:
            raise SystemExit("the page did not get ready: %s\n%s"
                             % (e, "\n".join(self.console[-20:]))) from None
        failed = self.page.evaluate("window.smtv.failed")
        if failed:
            raise SystemExit("the page could not start: %s" % failed)
        self.ready_after = time.monotonic() - started
        self.runtime = self.page.evaluate("window.smtv.runtime")
        if len(self.page.workers) != 1:
            raise SystemExit("the page started %d workers; this counts one" % len(self.page.workers))
        self.worker = self.page.workers[0]
        self.loaded = self.mark()

    def mark(self):
        return {"browser": len(self.requests), "server": self.server.count(),
                "page timing": len(self.page.evaluate(TIMING)),
                "worker timing": len(self.worker.evaluate(TIMING))}

    def since(self, mark):
        return {"browser": self.requests[mark["browser"]:],
                "server": [path for path, _ in self.server.since(mark["server"])],
                "page timing": self.page.evaluate(TIMING)[mark["page timing"]:],
                "worker timing": self.worker.evaluate(TIMING)[mark["worker timing"]:]}

    def asked_while_loading(self):
        """What the page fetched before it was ready, other than its own blobs."""
        return [u for u in self.requests[:self.loaded["browser"]]
                if not u.startswith(("blob:", "data:"))]

    def controls(self, base):
        """Make the page and the worker fetch once each, and see who noticed."""
        mark = self.mark()
        self.page.evaluate("fetch('%scontrol/page').then(r => r.status, e => String(e))" % base)
        self.worker.evaluate("fetch('%scontrol/worker').then(r => r.status, e => String(e))" % base)
        time.sleep(1)
        wanted = {base + "control/page", base + "control/worker", "/control/page", "/control/worker"}
        seen = self.since(mark)
        counted = {name: sum(1 for url in urls if url in wanted) for name, urls in seen.items()}
        stray = {name: [u for u in urls if u not in wanted] for name, urls in seen.items()}
        return counted, {name: urls for name, urls in stray.items() if urls}


#: Each counter, and how many of the two control requests it should see: the
#: page's own timing cannot see the worker's, nor the worker's the page's.
CONTROLS = {"browser": 2, "server": 2, "page timing": 1, "worker timing": 1}


def judge(watched, label, todo, expected, base, problems, run_page=page_runs) -> tuple:
    """Every file through one open page; then the counts, then the controls."""
    opened = sorted(path.name for path in todo if path.name in DOORS)
    if opened != sorted(DOORS):
        problems.append("%s: the files judged do not include every file that asks the reader "
                        "to reach the server (%s), so the count below says nothing about a "
                        "reader that was asked to" % (label, ", ".join(DOORS)))
    if sorted(path.name for path in todo if path.name in DEEP) != sorted(DEEP):
        problems.append("%s: the files judged do not include both documents nested past the "
                        "bound (%s), so nothing here says the page refuses them as the "
                        "command does" % (label, ", ".join(DEEP)))
    own = watched.asked_while_loading()
    if own != [watched.url]:
        problems.append("%s: while loading, the page asked for %s; it should ask for itself "
                        "and nothing else" % (label, own))
    runs = {path: run_page(watched.page if hasattr(watched, "page") else None, path)
            for path in todo}
    time.sleep(0 if run_page is not page_runs else 1)
    sent = watched.since(watched.loaded)
    for name, urls in sent.items():
        if urls:
            problems.append("%s: %d request(s) after load, seen by the %s counter: %s"
                            % (label, len(urls), name, urls[:5]))
    counted, stray = watched.controls(base)
    for name in blind(CONTROLS, counted):
        problems.append("%s: the %s counter did not see the control requests, so the zero "
                        "it read proves nothing" % (label, name))
    for name, urls in stray.items():
        problems.append("%s: requests beside the controls, seen by the %s counter: %s"
                        % (label, name, urls[:5]))
    if watched.downloads:
        problems.append("%s: the page started %d download(s) by itself"
                        % (label, len(watched.downloads)))
    compared = 0
    for path in todo:
        for as_json, run in zip((False, True), runs[path]):
            compared += 1
            for line in differences(run, expected[(path, as_json)]):
                problems.append("%s: %s (%s): %s"
                                % (label, path.name, "-f json" if as_json else "text", line))
    return runs, compared, sum(len(urls) for urls in sent.values())


def installs_nothing(context, watched, label, problems):
    """No cookie and no local storage, as the browser context reports them,
    and -- where a page could have them at all -- no service worker and no
    cache. A document opened from a disk cannot register either: the browser
    refuses the question for it. IndexedDB and the origin's private file
    system are not asked."""
    state = context.storage_state()
    if state.get("cookies") or state.get("origins"):
        problems.append("%s: the page left something stored: %s" % (label, state))
    if not watched.url.startswith("http"):
        return
    registered = watched.page.evaluate(
        "navigator.serviceWorker ? navigator.serviceWorker.getRegistrations().then(r => r.length) : 0")
    cached = watched.page.evaluate("self.caches ? caches.keys().then(k => k.length) : 0")
    if registered or cached:
        problems.append("%s: service workers %s, caches %s" % (label, registered, cached))


def shows_what_was_compared(watched, last, label, problems):
    """What a person reads and saves is what was compared: the report on the
    page, and the JSON behind its link, for the last file judged."""
    text, as_json = last
    shown = watched.page.evaluate("document.getElementById('report').textContent")
    if shown != text.stdout.decode("utf-8"):
        problems.append("%s: the report on the page is not the bytes it was compared on" % label)
    with watched.page.expect_download() as download:
        watched.page.click("#json")
    if Path(download.value.path()).read_bytes() != as_json.stdout:
        problems.append("%s: the JSON a person saves is not the JSON that was compared" % label)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--page", default=str(PAGE))
    ap.add_argument("--only", nargs="*", help="judge these files instead of everything here")
    args = ap.parse_args()

    page_file = Path(args.page).resolve()
    if sync_playwright is None:
        print("Playwright is not installed. This gate needs it and one browser:\n"
              "    python -m pip install \"playwright==%s\"\n"
              "    python -m playwright install chromium" % PLAYWRIGHT, file=sys.stderr)
        return 2
    if not page_file.is_file():
        print("there is no page at %s to judge; build it with "
              "`python tools/build_browser.py`" % page_file, file=sys.stderr)
        return 2

    argv_for = _the_pages_python().argv_for
    here = versions_here()
    problems = []
    server = Server(page_file)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            todo = ([Path(p).resolve() for p in args.only] if args.only
                    else inputs(Path(tmp) / "inputs"))
            todo = todo + doors(Path(tmp) / "doors", server.base) + deep(Path(tmp) / "deep")

            # The command first, with the server already up: anything asked of
            # the server now is the command's doing, not the page's.
            mark = server.count()
            jobs = [(path, as_json) for path in todo for as_json in (False, True)]
            with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 2) as pool:
                expected = dict(zip(jobs, pool.map(
                    lambda job: command(argv_for(job[0].name, job[1]), job[0].parent), jobs)))
            if server.since(mark):
                problems.append("the command reached the server: %s" % server.since(mark)[:5])

            with sync_playwright() as p:
                browser = p.chromium.launch()
                try:
                    for label, url in (("served", server.base + page_file.name),
                                       ("opened from a disk", page_file.as_uri())):
                        context = browser.new_context(accept_downloads=True)
                        watched = Watched(context, url, server)
                        mismatch = unlike(watched.runtime, here)
                        if mismatch:
                            print("the page runs %s and the command here %s; they differ in %s, "
                                  "so a difference between their reports could not be told "
                                  "apart from that. Run this on Python %s with the same "
                                  "packages." % (watched.runtime, here, mismatch,
                                                 watched.runtime.get("python")), file=sys.stderr)
                            return 2
                        runs, compared, sent = judge(watched, label, todo, expected,
                                                     server.base, problems)
                        installs_nothing(context, watched, label, problems)
                        shows_what_was_compared(watched, runs[todo[-1]], label, problems)
                        print("%s: ready in %.1f s; %d files, %d runs compared with the command; "
                              "requests after load: %d"
                              % (label, watched.ready_after, len(todo), compared, sent))
                        context.close()
                finally:
                    browser.close()
    finally:
        server.close()

    for line in problems:
        print("  %s" % line, file=sys.stderr)
    if problems:
        print("\n%d thing(s) the page says about itself did not hold." % len(problems),
              file=sys.stderr)
        return 1
    print("The page sent nothing after loading, installed nothing, and said what the "
          "command says about all %d files, served and opened from a disk." % len(todo))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
