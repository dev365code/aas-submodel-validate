# Everything CI's lint and test gates run, runnable before you push, because a
# gate that exists in one place and not the other fails quietly in the
# dangerous direction. tests/test_ci_parity.py holds the two in step.

RUFF_VERSION := 0.16.3
PYTHON       ?= python3
export PYTHONPATH := $(CURDIR)/src:$(CURDIR)/tests

.PHONY: help check test lint fix dev generated vendored exercised

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

generated:
	$(PYTHON) tools/extract_smt_rules.py --check

vendored:
	$(PYTHON) tools/vendor_template.py --check

exercised:
	$(PYTHON) tools/rule_coverage.py --check

battery-data:
	$(PYTHON) tools/battery_data_check.py

lint:
	@$(PYTHON) -m ruff --version | grep -q "$(RUFF_VERSION)" \
		|| { echo "ruff $(RUFF_VERSION) required (make dev)"; exit 1; }
	$(PYTHON) -m ruff check .

test:
	$(PYTHON) -m pytest -q

fix:
	$(PYTHON) -m ruff check --fix .

dev:
	$(PYTHON) -m pip install --user "ruff==$(RUFF_VERSION)" "pytest>=7" "aas-core3.0>=1.1.4,<2"
