# Everything CI's lint and test gates run, runnable before you push, because a
# gate that exists in one place and not the other fails quietly in the
# dangerous direction. tests/test_ci_parity.py holds the two in step.

RUFF_VERSION := 0.16.3
PYTHON       ?= python3
export PYTHONPATH := $(CURDIR)/src:$(CURDIR)/tests

.PHONY: help check ci-axes test lint fix dev generated vendored exercised

help:
	@echo "make check   everything CI runs: lint, gates, the test suite"
	@echo "make test    the test suite alone"
	@echo "make lint    ruff, pinned to the version CI uses"
	@echo "make generated  the generated rule table still matches its generator"
	@echo "make vendored   the vendored official material matches its hashes"
	@echo "make exercised  every rule id fired somewhere in the suite"
	@echo "make fix     ruff --fix, for what it can correct itself"
	@echo "make dev     install the pinned dev tools"

check: lint generated vendored battery-data test exercised

# The two things CI can see and `check` cannot: which tree the suite
# runs from, and which interpreter runs it. Both have gone red on a
# green `check`. Not folded into `check` -- it builds a distribution and
# installs into throwaway environments, which is too slow for every
# edit. Run it before a push.
ci-axes:
	sh tools/ci_axes.sh

generated:
	$(PYTHON) tools/extract_smt_rules.py --check

vendored:
	$(PYTHON) tools/vendor_template.py --check
	$(PYTHON) tools/gen_door.py --check

exercised:
	$(PYTHON) tools/rule_coverage.py --check

battery-data:
	$(PYTHON) tools/battery_data_check.py
	cd data/battery-passport && $(PYTHON) tools/join_requirements.py --dir . \
		--out requirements-join.json --md requirements-join.md --check
	$(PYTHON) tools/extract_battery_rules.py --check

# `--no-cache` on both sides. A linter that answers from a cache can
# answer about a file that has moved, and then the local gate is green
# over a tree CI reads differently -- reported by a sibling project,
# which met it after a rename. It could not be reproduced on the ruff
# pinned here, so this is adopted for the reason that survives either
# way: the two invocations have to be the same check, and a cache is a
# difference between them that nobody can see.
lint:
	@$(PYTHON) -m ruff --version | grep -qx "ruff $(RUFF_VERSION)" \
		|| { echo "ruff $(RUFF_VERSION) required (make dev)"; exit 1; }
	$(PYTHON) -m ruff check --no-cache .

test:
	$(PYTHON) -m pytest -q

fix:
	$(PYTHON) -m ruff check --no-cache --fix .

dev:
# `--user` is refused inside a virtualenv -- "Can not perform a '--user'
# install" -- which is where a contributor most likely is, and it
# installed neither the package nor the battery readers, so `make check`
# straight after `make dev` could not pass. The extras are the
# declaration; this target is one way of reading it.
	$(PYTHON) -m pip install -e ".[dev,battery]"
