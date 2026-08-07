# Public Release Checklist

Use this before pushing a public fork.

- Confirm `.env` contains no real keys and is ignored.
- Confirm generated files under `data/user/` are ignored.
- Confirm downloaded papers or PDFs are not committed.
- Run `python3 -m py_compile code/*.py`.
- Run the headless smoke test from the README or final Codex summary.
- Review `git status --short --ignored` before pushing.
