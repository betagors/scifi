# Contributing to SciFi

Thank you for your interest in contributing to **SciFi**! SciFi is built to enforce zero-hallucination academic standards, mathematical rigor, and publication-grade LaTeX typesetting across AI coding assistants and terminal workflows.

---

## 🛠️ Development Environment Setup

SciFi requires **Python ≥ 3.12** and [`uv`](https://docs.astral.sh/uv/).

```bash
# 1. Clone the repository
git clone https://github.com/Betagors/scifi.git
cd scifi

# 2. Install dependencies (including dev dependencies)
uv sync --extra dev

# 3. Run the test suite
uv run pytest tests/ -v
```

---

## 🏛️ Architecture & Design Principles

SciFi follows a **Tripartite Architecture**:
1. **Deterministic Tools (`scifi/`)**: FastMCP tools and CLI modules that perform exact verification (Crossref/OpenAlex/arXiv lookups, SymPy symbolic calculus, Pint dimensional checks, SciPy statistical audits, multi-file LaTeX resolution, and `latexmk` compilation).
2. **Cognitive Skills (`skills/<name>/SKILL.md`)**: On-demand playbooks that instruct AI agents on how to orchestrate the deterministic tools.
3. **Academic Invariants (`rules/AGENTS.md`)**: Compact always-on scholarly standards for the Antigravity plugin (and synced to workspace `AGENTS.md` via `uv run sf sync`).

### Key Guidelines for Contributors
- **Zero External Hallucinations**: Every citation or metadata tool must verify against authoritative registries or local SQLite cache (`scifi/cache.py` / `scifi/literature/store.py`).
- **Multi-File LaTeX Awareness**: Manuscript tools must support multi-file LaTeX projects (`main.tex` + `\input{sections/...}`) using `scifi.latex.project.resolve_latex_project`.
- **Full CLI & FastMCP Parity**: New capabilities should be exposed both as a typed tool in `scifi/server.py` and as a subcommand in `scifi/cli.py`.
- **Offline-Safe Unit Tests**: All unit tests in `tests/` must be deterministic and mock external HTTP calls where appropriate so CI runs fast and reliably without network flakiness.

---

## 🧪 Submitting Pull Requests

1. Create a feature branch (`git checkout -b feat/your-feature`).
2. Add comprehensive unit tests in `tests/` covering edge cases.
3. Verify all tests pass (`uv run pytest tests/ -v`).
4. If you modified `rules/AGENTS.md`, run `uv run sf sync` to keep all agent rule files synchronized.
5. Open a Pull Request with a clear summary of changes.
