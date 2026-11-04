# UFC fight predictor — task runner.
#
# Conventions:
#   - Everything runs as `PYTHONPATH=. .venv/bin/python ...`.
#   - The venv's pip shebang is broken (repo was moved): never call .venv/bin/pip
#     directly — always `.venv/bin/python -m pip`.

PY := .venv/bin/python

.PHONY: setup test lint typecheck format smoke predict ci

## setup: create the venv (if missing) and install requirements
setup:
	test -x $(PY) || python3 -m venv .venv
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -r requirements.txt

## test: run the test suite (data-dependent tests skip when artifacts are absent)
test:
	PYTHONPATH=. $(PY) -m pytest tests/ -q

## lint: ruff over the whole repo
lint:
	$(PY) -m ruff check .

## typecheck: mypy over src/
typecheck:
	$(PY) -m mypy src

## format: apply ruff autofixes
format:
	$(PY) -m ruff check --fix .

## smoke: fast end-to-end training smoke run (tiny slice, no artifact overwrite)
smoke:
	PYTHONPATH=. $(PY) scripts/train_all.py --smoke

## predict: example prediction through the public API
predict:
	PYTHONPATH=. $(PY) -c "from datetime import date; from src.api.predict_fight import predict_fight; print(predict_fight('Islam Makhachev', 'Charles Oliveira', date(2025, 4, 12), weight_class='Lightweight').to_markdown())"

## ci: everything the CI workflow runs
ci: lint typecheck test
