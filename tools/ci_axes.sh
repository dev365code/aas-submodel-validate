#!/bin/sh
# The two things CI can see and `make check` cannot.
#
# `make check` runs the suite from this checkout on this interpreter, and
# that has been green while CI was red -- once because an sdist carries
# the generated table and none of the indexes the tests read, and once
# because `pathlib.os` is a binding some Pythons expose and others do
# not. Neither is reachable from where `make check` stands: the first is
# a fact about which tree the suite runs from, the second about which
# interpreter runs it.
#
# So this builds the tree CI builds and runs the suite on every
# versioned interpreter present. Measure the axis rather than trust the
# one point you are standing on.
#
# Not folded into `make check` -- it builds a distribution and installs
# into a throwaway environment, which is too slow to run on every edit.
# Run it before a push.
set -e
ROOT=$(cd "$(dirname "$0")/.." && pwd)
WORK=${TMPDIR:-/tmp}/ci-axes-$$
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK"

echo "== axis 1: the suite from an unpacked sdist, as MANIFEST.in promises"
cd "$ROOT"
"${PYTHON:-python3}" -m build --sdist --outdir "$WORK/dist" >"$WORK/build.log" 2>&1 \
  || { echo "   sdist build failed:"; tail -5 "$WORK/build.log"; exit 1; }
cd "$WORK"
tar xzf dist/*.tar.gz
cd aas_submodel_validate-*/
PYTHONPATH=src "${PYTHON:-python3}" -m pytest tests/ -q >"$WORK/sdist.log" 2>&1 \
  || { echo "   FAILED from an unpacked sdist:"; grep -E "^FAILED|^E " "$WORK/sdist.log" | head -8; exit 1; }
echo "   $(tail -1 "$WORK/sdist.log")"

echo "== axis 2: every interpreter on this machine, not the newest one"
# The newest is not a superset, measured here: `pathlib.os` exists on
# 3.9 and 3.12, is gone on 3.13 and is back on 3.14, and
# `Path.exists()` raises on an untraversable parent through 3.13 and
# returns False on 3.14. A gate that ran only the newest would have
# missed the 3.13 fault it was written for -- twice over, since 3.14
# both restores the binding and skips the test that would have caught
# it. So: all of them.
FOUND=0
for v in 3.9 3.10 3.11 3.12 3.13 3.14; do
    WHERE=""
    for candidate in "$HOME/.local/bin/python$v" "/usr/bin/python$v" "$(command -v "python$v" 2>/dev/null)"; do
        [ -x "$candidate" ] && [ -z "$WHERE" ] && WHERE="$candidate"
    done
    [ -z "$WHERE" ] && continue
    FOUND=$((FOUND + 1))
    VENV="$WORK/venv-$v"
    "$WHERE" -m venv "$VENV" >/dev/null 2>&1 || { echo "   python$v: no venv, skipped"; continue; }
    "$VENV/bin/pip" -q install pytest "aas-core3.0>=1.1.4,<2" >"$WORK/pip-$v.log" 2>&1 \
      || { echo "   python$v: dependencies would not install, skipped"; continue; }
    cd "$ROOT"
    PYTHONPATH=src "$VENV/bin/python" -m pytest tests/ -q >"$WORK/py-$v.log" 2>&1 \
      || { echo "   FAILED on python$v:"; grep -E "^FAILED|^E " "$WORK/py-$v.log" | head -6; exit 1; }
    echo "   python$v  $(tail -1 "$WORK/py-$v.log")"
done
if [ "$FOUND" -eq 0 ]; then
    echo "   no versioned interpreter found; CI covers 3.9 to 3.13 and this"
    echo "   axis is unmeasured here -- install one to close it"
fi

echo "== both axes green"
