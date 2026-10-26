# Repository Guidelines
## Project Structure & Module Organization
The automation entry point is `src/fast_login.py`, which orchestrates the captive-portal check and login POST request. Shared configuration belongs in `src/configs.py`; keep credentials out of source control and load them from the environment (see `.env.example`). Add future helpers under `src/` using feature-based modules, and prefer small, testable functions. Store integration fixtures or mock responses under `tests/fixtures` when they are introduced.

## Build, Test, and Development Commands
Use Python 3.11+. Create an isolated environment with `python -m venv .venv` and activate it before installing packages. Install dependencies with `python -m pip install requests` and record them in `requirements.txt` for reproducibility. Run the script locally with `python src/fast_login.py`, which preserves relative imports. Pass `--help` flags through `python src/fast_login.py --help` once CLI arguments are added.

## Coding Style & Naming Conventions
Follow PEP 8: four-space indentation, snake_case for functions and variables, CamelCase for classes, and uppercase for constants such as `LOGIN_URL`. Group standard-library, third-party, and project imports separately. Prefer descriptive names that match the network domain (e.g., `dynamic_query_string`). Format new code with `ruff format` or `black` and lint with `ruff check`; keep line length <= 100 characters.

## Testing Expectations
Add unit tests in `tests/` mirroring the `src/` package layout (e.g., `tests/test_main.py`). Use `pytest` for assertions and fixtures; run it with `pytest -q`. Target coverage above 80%, focusing on dynamic query parsing and payload construction. Mock HTTP calls with `responses` or `requests-mock` so tests stay offline and deterministic.

## Commit & Pull Request Guidelines
Adopt Conventional Commits (e.g., `feat: add retry logic for login`) to highlight intent; the history is clean, so establish disciplined messages now. Keep commits small and focused. Pull requests must include a summary, testing notes (`pytest`, manual login), links to related issues, and screenshots or logs for notable behavioral changes. Highlight credential-handling considerations to help reviewers spot secrets before merge.

## Security & Configuration Tips
Never commit `.env`; store encrypted secrets or rely on system environment variables. Rotate campus credentials regularly and double-check that any logging redacts usernames and tokens. When sharing recordings or screenshots, mask IP addresses and query parameters because they often reveal device identifiers.
