#!/usr/bin/env python3
"""Generate the front door's two pictures: docs/assets/door.svg (the banner)
and docs/assets/verdict.svg (a real verdict, drawn).

The banner is mathematics -- a grid pulled toward a gravity well, an
event-horizon ring, one slow hotspot -- and carries no numbers, so it never
goes stale. The terminal shot is the actual output of the installed CLI on a
battery passport that conforms to its template and not to the regulation,
colour added; regenerate both on release.

The output is checked, not trusted: `--check` rebuilds both pictures and
fails if either differs from what is committed, and a test asserts that
every line of the terminal shot appears in the tool's own output. A picture
of a verdict that no longer matches the verdict is worse than no picture.

    python3 tools/gen_door.py            # write
    python3 tools/gen_door.py --check    # fail if the committed files differ
"""
from __future__ import annotations

import math
import pathlib
import sys

OUT = pathlib.Path(__file__).resolve().parent.parent / "docs" / "assets"
MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"
SANS = ("-apple-system,'Segoe UI',Roboto,'Helvetica Neue',Arial,"
        "'Apple SD Gothic Neo','Malgun Gothic',sans-serif")

# ── the banner ──────────────────────────────────────────────────────────────
CX, CY, W, H = 470.0, 100.0, 940, 408
A, S, EXT = 0.55, 165.0, 182


def _warp(x, y):
    dx, dy = x - CX, y - CY
    r = math.hypot(dx, dy)
    g = 1.0 - A * math.exp(-(r / S) ** 2)
    return CX + dx * g, CY + dy * g


def _grid():
    d = []
    for gx in range(-EXT, W + EXT + 1, 47):
        pts = [_warp(gx, gy) for gy in range(-EXT, H + EXT + 1, 8)]
        d.append("M" + "L".join("%.1f %.1f" % p for p in pts))
    for gy in range(-EXT, H + EXT + 1, 47):
        pts = [_warp(gx, gy) for gx in range(-EXT, W + EXT + 1, 8)]
        d.append("M" + "L".join("%.1f %.1f" % p for p in pts))
    return "".join(d)


def _smear():
    """The hotspot: four arcs of one ring, each fainter and longer than the
    last, so the leading edge reads as a head and the rest as its tail."""
    RR, SPAN, N = 57.0, 44.0, 4
    C = 2 * math.pi * RR
    segs = []
    seg = C * (SPAN / 360.0)
    for i in range(N):
        t = (i + 0.5) / N
        op = 0.55 * (1 - abs(t - 0.5) * 2)
        off = -C * (SPAN / 360.0) * i / N
        segs.append('<circle cx="470" cy="100" r="%.1f" fill="none" stroke="#ffeede" '
                    'stroke-opacity="%.3f" stroke-width="18" '
                    'stroke-dasharray="%.2f %.2f" stroke-dashoffset="%.2f"/>'
                    % (RR, op, seg, C - seg, off))
    return "".join(segs)


BANNER = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 940 408" role="img" aria-label="aas-submodel-validate — Asset Administration Shell submodels, judged against their IDTA template, offline">
<defs>
<radialGradient id="halo" cx="50%%" cy="50%%" r="50%%"><stop offset="0%%" stop-color="#2f5d8a" stop-opacity=".30"/><stop offset="100%%" stop-color="#2f5d8a" stop-opacity="0"/></radialGradient>
<filter id="soft"><feGaussianBlur stdDeviation="2.2"/></filter>
<filter id="softer"><feGaussianBlur stdDeviation="5"/></filter>
<filter id="smear" x="-40%%" y="-40%%" width="180%%" height="180%%"><feGaussianBlur stdDeviation="3"/></filter>
</defs>
<rect width="940" height="408" fill="#0b0f14"/>
<path d="%(grid)s" fill="none" stroke="rgba(198,212,224,0.075)" stroke-width="1"/>
<circle cx="470" cy="100" r="230" fill="url(#halo)"/>
<circle cx="470" cy="100" r="58" fill="none" stroke="#8fb8dd" stroke-opacity=".28" stroke-width="7" filter="url(#softer)"/>
<circle cx="470" cy="100" r="51" fill="#03050a"/>
<circle cx="470" cy="100" r="57" fill="none" stroke="#ffeede" stroke-opacity=".45" stroke-width="2" filter="url(#soft)"/>
<g filter="url(#smear)">%(smear)s
<animateTransform attributeName="transform" type="rotate" from="0 470 100" to="360 470 100" dur="16s" repeatCount="indefinite"/></g>
<text x="470" y="206" font-family="%(mono)s" font-size="12.5" letter-spacing="3.4" fill="#93a1ad" text-anchor="middle">STANDARDS, JUDGED OFFLINE</text>
<text x="470" y="262" font-family="%(mono)s" font-size="40" font-weight="700" fill="#e8edf2" text-anchor="middle">aas-submodel-validate<tspan fill="#8fb8dd">.</tspan></text>
<text x="470" y="292" font-family="%(sans)s" font-size="15.5" fill="#c6d2dc" text-anchor="middle">Asset Administration Shell submodels, judged against their</text>
<text x="470" y="313" font-family="%(sans)s" font-size="15.5" fill="#c6d2dc" text-anchor="middle">IDTA template — offline, and every finding tells you how to fix it.</text>
<text x="470" y="345" font-family="%(mono)s" font-size="15" font-weight="700" fill="#e8edf2" text-anchor="middle">AI proposes. <tspan fill="#8fb8dd">Rules judge.</tspan> People decide.</text>
<text x="470" y="376" text-anchor="middle" font-family="%(sans)s" font-size="12" fill="#93a1ad"><tspan font-family="%(mono)s" font-size="10.5" font-weight="700" fill="#7da7cf">DE&#160;&#160;</tspan>Prüft AAS-Teilmodelle offline<tspan font-family="%(mono)s" font-size="10.5" font-weight="700" fill="#ddab74">&#160;&#160;&#160;&#160;&#160;KO&#160;&#160;</tspan>AAS 서브모델 오프라인 판정</text>
</svg>'''


def banner() -> str:
    return BANNER % {"grid": _grid(), "smear": _smear(), "mono": MONO, "sans": SANS}


# ── the real verdict, drawn ─────────────────────────────────────────────────
#: Every string below is a substring of what the installed tool prints for
#: this input, and `tests/test_door.py` asserts exactly that against a live
#: run. Wrapping is the picture's own -- the terminal wraps where the window
#: ends and an SVG has no window -- so the test compares the joined text.
G, D, E, A_, F, T, N = "#8fd0a8", "#7d8a99", "#e0604d", "#e8c268", "#5cb87f", "#d8dfe5", "#93a1ad"

VERDICT_LINES = [
    (21, [(28, G, "$ ", 1), (46, T, "pip install aas-submodel-validate", 0)]),
    (30, [(28, G, "$ ", 1), (46, T, "smtv --allow-unmatched --meta info battery-passport.json", 0)]),
    (19, [(28, A_, "warning ", 1), (100, A_, "BAT-R8", 1),
          (168, T, "conformant to the template and not to the regulation:", 0)]),
    (19, [(168, T, "'EnergyRoundTripEfficiencyFade' is absent", 0)]),
    (17, [(140, N, "at", 1), (168, D, "TechnicalData/EnergyRoundTripEfficiencyFade", 0)]),
    (17, [(140, N, "saw", 1), (168, D, "IDTA 02035-4 V1.0.1 makes it ZeroToOne;", 0)]),
    (17, [(168, D, "Annex IV Part A (4) requires it", 0)]),
    (17, [(140, N, "per", 1), (168, D, "Regulation (EU) 2023/1542 Annex VII", 0)]),
    (17, [(140, N, "fix", 1), (168, F, "Provide the element, or record that this battery is", 0)]),
    (26, [(168, F, "outside the provision that requires it.", 0)]),
    (19, [(140, N, "note", 1), (180, N, "8 more are known to disagree and are not reported,", 0)]),
    (24, [(180, N, "because whether the law requires them depends on a category", 0)]),
    (19, [(28, T, "0 error(s), 1 warning(s), 3 info", 1),
          (280, N, "battery-passport.json · judged 0 of 1 submodel", 0)]),
]

SHOT = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 940 %(h)d" role="img" aria-label="Real smtv output on a battery passport: one warning, BAT-R8, conformant to the template and not to the regulation, with the element named, the clause cited and a remedy">
<rect x="1" y="1" width="938" height="%(inner)d" rx="10" fill="#12161a" stroke="#252b30" stroke-width="1.5"/>
<circle cx="24" cy="19" r="5" fill="#e0604d"/><circle cx="42" cy="19" r="5" fill="#e8c268"/><circle cx="60" cy="19" r="5" fill="#5cb87f"/>
<text x="80" y="23" font-family="%(mono)s" font-size="11" fill="#7d8a99">smtv — real output, colour added</text>
%(lines)s
</svg>'''


def verdict() -> str:
    rendered, y = [], 40
    for dy, runs in VERDICT_LINES:
        parts = "".join(
            '<tspan x="%d" fill="%s"%s>%s</tspan>'
            % (x, colour, ' font-weight="700"' if bold else "", text)
            for x, colour, text, bold in runs)
        rendered.append('<text y="%d" font-family="%s" font-size="12.5" '
                        'xml:space="preserve">%s</text>' % (y, MONO, parts))
        y += dy
    height = y + 18
    return SHOT % {"h": height, "inner": height - 2, "mono": MONO,
                   "lines": "".join(rendered)}


PICTURES = {"door.svg": banner, "verdict.svg": verdict}


def main(argv) -> int:
    checking = "--check" in argv
    OUT.mkdir(parents=True, exist_ok=True)
    stale = []
    for name, draw in PICTURES.items():
        drawn = draw()
        path = OUT / name
        if checking:
            if not path.is_file() or path.read_text(encoding="utf-8") != drawn:
                stale.append(name)
            continue
        path.write_text(drawn, encoding="utf-8")
        print("%s  %d KB" % (name, len(drawn) // 1024))
    if stale:
        print("out of date, regenerate with tools/gen_door.py: %s"
              % ", ".join(stale), file=sys.stderr)
        return 1
    if checking:
        print("door pictures match their generator")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
