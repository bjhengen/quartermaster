# Quartermaster

Self-hosted personal AI assistant with plugin architecture.

## Project Structure
- `src/quartermaster/` — Core application (do not modify lightly)
- `plugins/` — Plugin packages (each is self-contained)
- `config/` — YAML configuration (settings.yaml is gitignored)
- `credentials/` — API keys, OAuth tokens (gitignored)
- `tests/` — pytest test suite

## Development
- Python 3.13, strict mypy, ruff linting
- Run tests: `pytest`
- Type check: `mypy src/`
- Lint: `ruff check src/ plugins/ tests/`
- All data structures use Pydantic v2 models
- Structured logging via structlog (JSON format)

## Architecture
- Everything is a tool registered in the Tool Registry
- Plugins register tools at startup via PluginContext
- LLM is an orchestrator (selects tools), not a worker
- Event bus for loose coupling between components
- Oracle 26ai PDB for all persistence (no SQLite)

## Testing
- TDD: write failing test first, then implement
- Core services: unit tests with mocks
- Database: integration tests against QUARTERMASTER_TEST_PDB
- Each plugin tested in isolation against mock PluginContext

## Key Files
- `src/quartermaster/core/app.py` — Application bootstrap
- `src/quartermaster/core/tools.py` — Tool Registry (central nervous system)
- `src/quartermaster/core/events.py` — Event bus
- `src/quartermaster/llm/router.py` — Smart LLM routing
- `src/quartermaster/plugin/base.py` — Plugin base class
