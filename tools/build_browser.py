#!/usr/bin/env python3
"""Build the browser form: `aas-submodel-validate.html`, one page that judges a
submodel where it is opened.

Why it exists. The single file still needs a Python, and a machine that may
not have one installed may still have to look at a supplier's file. A browser
is on every such machine, and a page that runs the check inside the tab takes
the file nowhere: it is read where the page is open.

    python tools/build_browser.py                    # dist/aas-submodel-validate.html
    python tools/build_browser.py --runtime FILE     # with the runtime release already here

Everything the check needs is inside the page: this engine and its rules,
copied from this tree the way the single file copies them; aas-core3.0, from
the one wheel pinned below; and Pyodide, a build of CPython that runs in the
browser, with its standard library and the one module of it the engine needs
that the runtime ships apart. The page asks for nothing to start. Opened from
a disk it makes no request at all, and served it makes one, for itself.
`tools/browser_gates.py` holds it to that, and to giving the command's report
byte for byte.

Needs the network once, as the single file does: for the runtime, the module
it ships apart, the wheel and the notices -- each pinned by its digest and
refused if it differs. No resolver stands between a pin and the page: the
commit decides the bytes.
"""
from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import html
import io
import json
import re
import shutil
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BROWSER = ROOT / "browser"
SOURCE = ROOT / "src" / "aas_submodel_validate"
OUTPUT = ROOT / "dist" / "aas-submodel-validate.html"
sys.path.insert(0, str(ROOT / "tools"))
import build_zipapp  # noqa: E402 -- one filter and one timestamp for both single files

#: The runtime. A Pyodide release is a build of CPython for the browser, and
#: the page carries five files of it. The digest is the release asset's as
#: published; a download that differs from it is refused, not built.
RUNTIME = {
    "name": "Pyodide",
    "version": "0.29.5",
    "python": "3.13.2",
    "url": "https://github.com/pyodide/pyodide/releases/download/0.29.5/pyodide-core-0.29.5.tar.bz2",
    "sha256": "ab08aafc11a3c9a0fe73825eb2cec78bda9464348dd17414e7ec0132ef3451e8",
}
RUNTIME_FILES = ("pyodide.js", "pyodide.asm.js", "pyodide.asm.wasm", "python_stdlib.zip",
                 "pyodide-lock.json")

#: What the runtime keeps out of its standard library and the engine imports:
#: `lzma`, which reads a package part compressed with LZMA. The runtime ships
#: it as a package of its own, named with its digest in the release's lock
#: file; the pin here has to agree with that file or nothing is built.
RUNTIME_PACKAGES = (
    {"name": "lzma", "file": "lzma-1.0.0-cp313-cp313-pyemscripten_2025_0_wasm32.whl",
     "url": "https://cdn.jsdelivr.net/pyodide/v0.29.5/full/"
            "lzma-1.0.0-cp313-cp313-pyemscripten_2025_0_wasm32.whl",
     "sha256": "94930c9fa700c8fe26eddb49ab1ed36d3b06d77fdfc4287a1ef4299692d3d1d1"},
)

#: The one dependency, as one file: a version, the wheel and its digest.
WHEELS = (
    {"name": "aas-core3.0", "version": "1.1.4", "licence": "MIT",
     "url": "https://files.pythonhosted.org/packages/70/41/"
            "4dabc8be15dc8335579e91bada50ef3cf1a1be298817d4be500b7c1460fe/"
            "aas_core3_0-1.1.4-py3-none-any.whl",
     "sha256": "a6e9554f8e3ee129a8d238b817b6dbde8edc789720330bc4893c009511947de4"},
)

#: The notices of what the runtime is built from, at the revisions it was
#: built from. The release asset carries none of them, so they are fetched,
#: pinned the same way, and printed in the page. Not only Pyodide and
#: CPython: the `.wasm` has compiled into it what CPython incorporates --
#: expat, libmpdec, zlib, HACL* and the rest its licence page lists -- and,
#: from the build Pyodide made of it (its `Makefile.envs` and
#: `cpython/Makefile` at that tag), Pyodide's hiwire, libffi at the commit it
#: names, and Emscripten 4.0.9 with the musl it carries and its port of
#: bzip2; and the lzma package has liblzma built into it, from the xz
#: release `packages/liblzma/meta.yaml` names at that tag. `revision` is the
#: tag or commit each is read at; `between` cuts a notice out of a source
#: file that keeps it at its head.
RUNTIME_LICENCES = (
    {"name": "Pyodide", "notice": "Pyodide", "version": "0.29.5", "revision": "0.29.5",
     "licence": "MPL-2.0", "file": "LICENSE",
     "source": "https://github.com/pyodide/pyodide/tree/0.29.5",
     "url": "https://raw.githubusercontent.com/pyodide/pyodide/0.29.5/LICENSE",
     "sha256": "1f256ecad192880510e84ad60474eab7589218784b9a50bc7ceee34c2b91f1d5"},
    {"name": "hiwire, which Pyodide compiles into the runtime", "notice": "hiwire",
     "version": "6a1e672", "revision": "6a1e67280a15d929ebeceee54a6358c9c8d5f697",
     "licence": "MPL-2.0", "file": "LICENSE",
     "source": "https://github.com/pyodide/hiwire/tree/6a1e67280a15d929ebeceee54a6358c9c8d5f697",
     "url": "https://raw.githubusercontent.com/pyodide/hiwire/"
            "6a1e67280a15d929ebeceee54a6358c9c8d5f697/LICENSE",
     "sha256": "1f256ecad192880510e84ad60474eab7589218784b9a50bc7ceee34c2b91f1d5"},
    {"name": "CPython, with its standard library", "notice": "CPython", "version": "3.13.2",
     "revision": "v3.13.2", "licence": "PSF-2.0", "file": "LICENSE",
     "source": "https://github.com/python/cpython/tree/v3.13.2",
     "url": "https://raw.githubusercontent.com/python/cpython/v3.13.2/LICENSE",
     "sha256": "78b12c3a81360b357002334f0e70ea0e92eebf7a9b358805c03c48484945f3bb"},
    {"name": "What CPython incorporates: expat, libffi, zlib, libmpdec, mimalloc and the "
             "rest its licence page lists", "notice": "CPython incorporates",
     "version": "3.13.2", "revision": "v3.13.2", "licence": "each one's own, as given there",
     "file": "Doc/license.rst",
     "source": "https://github.com/python/cpython/tree/v3.13.2",
     "url": "https://raw.githubusercontent.com/python/cpython/v3.13.2/Doc/license.rst",
     "sha256": "62f2c9c2c75d511170eb464ad5f83b78cc1f37eb2eb49c2846c9aa6c4557ee99"},
    {"name": "HACL*, as CPython carries it", "notice": "HACL*", "version": "3.13.2",
     "revision": "v3.13.2", "licence": "MIT",
     "file": "Modules/_hacl/Hacl_Hash_SHA2.c, its notice",
     "source": "https://github.com/python/cpython/tree/v3.13.2/Modules/_hacl",
     "url": "https://raw.githubusercontent.com/python/cpython/v3.13.2/Modules/_hacl/Hacl_Hash_SHA2.c",
     "between": ("/* MIT License", "*/"),
     "sha256": "30638efb75c8b185bb09c3df6977e3f3c5d21a1e696218cf7ade6bc4d5201b31"},
    {"name": "libffi, which Pyodide compiles into the runtime", "notice": "libffi",
     "version": "f08493d", "revision": "f08493d249d2067c8b3207ba46693dd858f95db3",
     "licence": "MIT", "file": "LICENSE",
     "source": "https://github.com/libffi/libffi/tree/f08493d249d2067c8b3207ba46693dd858f95db3",
     "url": "https://raw.githubusercontent.com/libffi/libffi/"
            "f08493d249d2067c8b3207ba46693dd858f95db3/LICENSE",
     "sha256": "2c9c2acb9743e6b007b91350475308aee44691d96aa20eacef8e199988c8c388"},
    {"name": "bzip2, as Emscripten's port builds it", "notice": "bzip2", "version": "1.0.6",
     "revision": "1.0.6", "licence": "bzip2's own, BSD-style", "file": "LICENSE",
     "source": "https://github.com/emscripten-ports/bzip2/tree/1.0.6",
     "url": "https://raw.githubusercontent.com/emscripten-ports/bzip2/1.0.6/LICENSE",
     "sha256": "4919cfb14a73cd64fcef67b107613970cf1659a09aa675dba31314f373bc7204"},
    {"name": "Emscripten, the compiler and runtime the build used", "notice": "Emscripten",
     "version": "4.0.9", "revision": "4.0.9", "licence": "MIT or University of Illinois/NCSA",
     "file": "LICENSE",
     "source": "https://github.com/emscripten-core/emscripten/tree/4.0.9",
     "url": "https://raw.githubusercontent.com/emscripten-core/emscripten/4.0.9/LICENSE",
     "sha256": "620a78084fc7ca97c0b5dea9abf891f3ffcadfdbf305276f099c9c4e12fc1d86"},
    {"name": "musl, the C library Emscripten carries", "notice": "musl", "version": "4.0.9",
     "revision": "4.0.9", "licence": "MIT", "file": "COPYRIGHT",
     "source": "https://github.com/emscripten-core/emscripten/tree/4.0.9/system/lib/libc/musl",
     "url": "https://raw.githubusercontent.com/emscripten-core/emscripten/4.0.9/"
            "system/lib/libc/musl/COPYRIGHT",
     "sha256": "f9bc4423732350eb0b3f7ed7e91d530298476f8fec0c6c427a1c04ade22655af"},
    {"name": "liblzma, from XZ Utils, which the runtime's lzma package is built with",
     "notice": "liblzma", "version": "5.2.2", "revision": "v5.2.2",
     "licence": "public domain, as its notice says", "file": "COPYING",
     "source": "https://github.com/tukaani-project/xz/tree/v5.2.2",
     "url": "https://raw.githubusercontent.com/tukaani-project/xz/v5.2.2/COPYING",
     "sha256": "c4f8e14fafe458d84808a4cd8b69f94673ebe2bf8fc992291629a69ac12218f8"},
)

#: The places in `browser/page.html` this fills, each exactly once.
MARKS = ("@@TITLE@@", "@@VERSION@@", "@@LICENCES@@", "@@ASSETS@@", "@@WORKER@@")

#: This project's own notices, as the single file carries them.
OWN_NOTICES = ("LICENSE", "NOTICE", "THIRD_PARTY.md")


def download(url: str) -> bytes:
    """The one way anything reaches this build from outside."""
    with urllib.request.urlopen(url, timeout=300) as answer:
        return answer.read()


def verified(data: bytes, sha256: str, what: str) -> bytes:
    got = hashlib.sha256(data).hexdigest()
    if got != sha256:
        raise SystemExit("%s has sha256 %s, and this build takes only %s. Nothing was "
                         "built. If the pin is what should move, move it here and say "
                         "why in the commit." % (what, got, sha256))
    return data


def fetch(url: str, sha256: str, what: str, local: Path = None) -> bytes:
    return verified(local.read_bytes() if local is not None else download(url), sha256, what)


def runtime_files(tarball: bytes) -> dict:
    """The files the page needs, out of the release asset, by the names the
    runtime's loader asks for."""
    found = {}
    with tarfile.open(fileobj=io.BytesIO(tarball), mode="r:bz2") as tar:
        for name in RUNTIME_FILES:
            try:
                member = tar.getmember("pyodide/" + name)
            except KeyError:
                raise SystemExit("the runtime release has no pyodide/%s" % name) from None
            found[name] = tar.extractfile(member).read()
    return found


def as_the_lock_names_them(lock: bytes) -> None:
    """Each package pinned here is the file, at the digest, the runtime's own
    lock file names -- or the page would carry what its runtime would not
    have loaded."""
    packages = json.loads(lock.decode("utf-8")).get("packages", {})
    for entry in RUNTIME_PACKAGES:
        locked = packages.get(entry["name"]) or {}
        if (locked.get("file_name"), locked.get("sha256")) != (entry["file"], entry["sha256"]):
            raise SystemExit("the runtime's lock file names %s as %s at %s, and this build "
                             "pins %s at %s; nothing was built"
                             % (entry["name"], locked.get("file_name"), locked.get("sha256"),
                                entry["file"], entry["sha256"]))


def script_safe(text: str, what: str) -> str:
    """Text that can sit inside a `<script>` element without ending it early."""
    if re.search(r"</script|<!--", text, re.IGNORECASE):
        raise SystemExit("%s contains `</script` or `<!--`, which would end or change the "
                         "script element it is put in" % what)
    return text


def assemble(template: str, fills: dict) -> str:
    """Fill each place in the page once, and refuse a page that has a place
    twice, or not at all, or a fill that would itself be read as a place."""
    for mark in MARKS:
        n = template.count(mark)
        if n != 1:
            raise SystemExit("%s appears %d times in the page; each place is filled once"
                             % (mark, n))
    for mark, text in fills.items():
        if any(other in text for other in MARKS):
            raise SystemExit("what fills %s contains a place of its own" % mark)
    for mark in MARKS:
        template = template.replace(mark, fills[mark])
    return template


def version() -> str:
    source = (SOURCE / "__init__.py").read_text(encoding="utf-8")
    return re.search(r'^__version__ = "([^"]+)"', source, re.M).group(1)


def stage(into: Path, wheels: dict) -> dict:
    """The tree the page runs from: the wheel's package, this engine and the
    page's own Python, with the project's notices. Returns each wheel's
    licence texts, read from its `.dist-info` before that is left out."""
    texts = {}
    for entry in WHEELS:
        with zipfile.ZipFile(io.BytesIO(wheels[entry["name"]])) as wheel:
            texts[entry["name"]] = {}
            for name in sorted(wheel.namelist()):
                top = name.split("/", 1)[0]
                if top.endswith(".dist-info"):
                    if "/licenses/" in name and not name.endswith("/"):
                        texts[entry["name"]][name.rsplit("/", 1)[1]] = \
                            wheel.read(name).decode("utf-8")
                    continue
                if name.endswith("/") or not build_zipapp.belongs(name):
                    continue
                target = into / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(wheel.read(name))
    shutil.copytree(SOURCE, into / SOURCE.name,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copyfile(BROWSER / "aas_page.py", into / "aas_page.py")
    for name in OWN_NOTICES:
        shutil.copyfile(ROOT / name, into / name)
    return texts


def app_archive(staged: Path) -> bytes:
    """The staged tree as one zip, entries in name order, every stamp the
    same, so one tree builds into one page."""
    stamp = build_zipapp._timestamp()
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(p for p in staged.rglob("*") if p.is_file()):
            name = path.relative_to(staged).as_posix()
            if not build_zipapp.belongs(name):
                continue
            info = zipfile.ZipInfo(name, date_time=stamp)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())
    return raw.getvalue()


def notice_text(data: bytes, between=None) -> str:
    """The notice a fetched file holds: all of it, or the part from the first
    `between[0]` to the `between[1]` after it."""
    text = data.decode("utf-8")
    if between is None:
        return text
    start = text.index(between[0])
    return text[start:text.index(between[1], start) + len(between[1])]


def licences_html(runtime: list, wheel_texts: dict) -> str:
    """Each component, its version, its licence, where its source is, and the
    licence text itself."""
    parts = []

    def one(title, licence, source, texts):
        parts.append("<p><strong>%s</strong> &mdash; %s%s</p>"
                     % (html.escape(title), html.escape(licence),
                        " &mdash; source: %s" % html.escape(source) if source else ""))
        for name, text in texts.items():
            parts.append('<pre aria-label="%s">%s</pre>' % (html.escape(name), html.escape(text)))

    one("aas-submodel-validate %s: this page, the engine, the rules and the IDTA material "
        "they are read from" % version(),
        "Apache-2.0, with the material THIRD_PARTY.md lists",
        "https://github.com/dev365code/aas-submodel-validate",
        {name: (ROOT / name).read_text(encoding="utf-8") for name in OWN_NOTICES})
    for entry in runtime:
        one("%s %s" % (entry["name"], entry["version"]), entry["licence"], entry["source"],
            {entry["file"]: entry["text"]})
    one("%s %s release asset" % (RUNTIME["name"], RUNTIME["version"]),
        "sha256 %s" % RUNTIME["sha256"], RUNTIME["url"], {})
    for entry in RUNTIME_PACKAGES:
        one("%s, the runtime's own package %s" % (entry["name"], entry["file"]),
            "sha256 %s; CPython's module, built with liblzma, both above" % entry["sha256"],
            entry["url"], {})
    for entry in WHEELS:
        one("%s %s" % (entry["name"], entry["version"]), entry["licence"],
            "https://pypi.org/project/%s/%s/" % (entry["name"], entry["version"]),
            wheel_texts[entry["name"]])
    return "\n".join(parts)


def build(output: Path, runtime_asset: Path = None) -> bytes:
    runtime = runtime_files(fetch(RUNTIME["url"], RUNTIME["sha256"],
                                  "the %s %s release" % (RUNTIME["name"], RUNTIME["version"]),
                                  runtime_asset))
    as_the_lock_names_them(runtime["pyodide-lock.json"])
    packages = {entry["file"]: fetch(entry["url"], entry["sha256"],
                                     "the runtime's %s package" % entry["name"])
                for entry in RUNTIME_PACKAGES}
    wheels = {entry["name"]: fetch(entry["url"], entry["sha256"],
                                   "the %s %s wheel" % (entry["name"], entry["version"]))
              for entry in WHEELS}
    licences = [dict(entry, text=notice_text(fetch(entry["url"], entry["sha256"],
                                                   "the %s notice" % entry["notice"]),
                                             entry.get("between")))
                for entry in RUNTIME_LICENCES]
    with tempfile.TemporaryDirectory() as tmp:
        staged = Path(tmp) / "app"
        staged.mkdir()
        wheel_texts = stage(staged, wheels)
        app = app_archive(staged)

    assets = dict(runtime, **packages, **{"app.zip": app})
    blocks = "\n".join(
        '<script type="application/gzip" data-asset="%s">%s</script>'
        % (name, base64.b64encode(gzip.compress(data, compresslevel=9, mtime=0)).decode("ascii"))
        for name, data in assets.items())
    page = assemble((BROWSER / "page.html").read_text(encoding="utf-8"), {
        "@@TITLE@@": "aas-submodel-validate %s — judge an AAS submodel in this browser" % version(),
        "@@VERSION@@": version(),
        "@@LICENCES@@": licences_html(licences, wheel_texts),
        "@@ASSETS@@": blocks,
        "@@WORKER@@": script_safe((BROWSER / "worker.js").read_text(encoding="utf-8"), "the worker"),
    }).encode("utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(page)
    return page


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-o", "--output", default=str(OUTPUT))
    ap.add_argument("--runtime", help="the runtime release asset, already downloaded; its "
                                      "digest is checked all the same")
    args = ap.parse_args()
    target = Path(args.output)
    page = build(target, Path(args.runtime) if args.runtime else None)
    print("%s (%s bytes)" % (target, format(len(page), ",")))
    print("sha256 %s" % hashlib.sha256(page).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
