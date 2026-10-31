# Notes for AI assistants

- Read [ARCHITECTURE.md](ARCHITECTURE.md) before changing code; [PLAN.md](PLAN.md) has status and limitations.
- Run everything with `.venv/bin/python` (system `python3` lacks the dependencies and Tk).
- This folder is the tool only. Downloaded cases live in section folders elsewhere (e.g.
  `~/Downloads/<section>`); don't write cases or digests here.
- The repo is public: no personal paths, names or institution details in code or docs; the user's own
  syllabi in `syllabi/` are gitignored (only `example-*` is tracked).
- Never commit `.cdasia_profile/` (session cookies), `settings.json`, or downloaded PDFs.
- Be gentle with CDAsia: keep `DELAY_S`, test with `--only <case>` into a scratch folder rather than full runs.
- If a syllabus format trips the parser, fix `syllabus_parser.py` (and note it in ARCHITECTURE.md) rather
  than hand-writing yaml.
- Writing digests is a separate task, driven by the section folder's `PROMPT.md` (default in `templates/`).
- Keep README.md (usage), ARCHITECTURE.md (design), PLAN.md (status) and CHANGELOG.md in step with changes.
  Diagrams are Graphviz in `docs/diagrams/*.dot`; after editing one, run `docs/diagrams/render.sh` and
  commit the `.svg` too.
