# Repository Guidelines

## Project Structure & Module Organization
The core add-on logic lives in `prioritysieve/`, with feature-focused modules such as `prioritysieve/recalc/` for rebuilding the entry database, `prioritysieve/generators/` for CSV tooling, and `prioritysieve/ui/` for Qt dialogs. Shared helpers (`prioritysieve/entry_db.py`, `prioritysieve/priority_gap_utils.py`, etc.) drive scheduling and tagging. Tests reside in `test/tests/` with fixtures and fakes in `test/fake_configs.py` and `test/data/`. Documentation for user-facing flows is maintained in `docs/`, and release packaging assets sit alongside scripts like `bundle_addon.sh`.

## Build, Test, and Development Commands
- `nix-shell` (or `nix develop` with flakes) loads `shell.nix`, exporting the Qt/GL dependencies Anki expects; once inside, create and activate a venv (`python -m venv .venv && source .venv/bin/activate`).  
- `python -m pip install -r requirements.txt` must be run from that venv for both dev and test shells so `anki`/`aqt` modules resolve.  
- `nix-shell test/tests-shell.nix --command "source .venv/bin/activate && pytest"` runs the suite with the offscreen Qt setup required by `qtbot`; add `--maxfail=1` locally to shorten feedback loops.  
- `python -m pytest -m recalc` focuses on recalculation scenarios; pair with `--maxfail=1` when chasing regressions.  
- `./bundle_addon.sh` strips caches, toggles `DEV_MODE` off, and emits `prioritysieve-<version>.ankiaddon` for distribution; run it from the repo root.  
For ad-hoc checks, `python -m black prioritysieve test` and `python -m isort prioritysieve test` keep formatting consistent.

## Coding Style & Naming Conventions
Python files follow Black’s defaults (88-character lines) with isort’s Black profile. Prefer snake_case for modules, functions, and variables; reserve PascalCase for Qt widgets and domain models. Static analysis is enforced via `mypy --strict`, and `pylint` runs with warnings relaxed for Anki-specific patterns. Keep UI resources in `prioritysieve/ui/` and avoid hard-coding profile paths—use helpers from `browser_utils.py` and `prioritysieve_globals.py`.

## Testing Guidelines
Write tests with pytest and the fixtures in `test/conftest.py`. Place new suites under `test/tests/` using the `*_test.py` naming rule and `test_*` functions. Mark slow UI interactions with `@pytest.mark.slow` or domain-specific tags like `recalc`, matching the configured markers. Run GUI-dependent tests via `nix-shell test/tests-shell.nix` (exports `QT_QPA_PLATFORM=offscreen`) after activating the shared `.venv`, and use fake environment helpers in `test/fake_environment_module.py` for deterministic dialogs.

## Commit & Pull Request Guidelines
Commit messages are short, present-tense statements (e.g., “Stub recalc success dependencies for tests”) and should cover the observable change. Squash noisy work-in-progress commits before opening a PR. Each PR should describe behavioural impact, reference related issues, and highlight UI changes or migrations with screenshots or sample CSVs when relevant. Confirm that bundles exclude local files like `prioritysieve/meta.json`, mention any configuration migrations in `docs/`, and link to updated documentation sections when behaviour shifts.
