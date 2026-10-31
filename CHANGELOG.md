# Changelog

## 2026-10-31

### Public release prep
- CDAsia URL configurable via `CDASIA_URL` (replaces `cdasialink.md`).
- Digest prompt and style sample moved to `templates/`; your own syllabi stay local (only `example-*` tracked).
- Paths shown as `~/…`; "Open folder" and editor font work on Windows/Linux too.
- README rewritten with screenshots; added LICENSE (MIT), ARCHITECTURE.md with Graphviz diagrams, PLAN.md,
  CLAUDE.md, this changelog.

### Syllabus input and review (`731c39a`)
- Give the UIs a syllabus `.md` instead of a yaml; `syllabus_parser.py` generates the case list.
- Review/edit the list before downloading (GUI editor tab; `$EDITOR` in the TUI); guesses marked `# CHECK:`.
- Section folders also get `syllabus.md`, `PROMPT.md`, `SAMPLE-DIGEST-STYLE-TO-FOLLOW.md`; `digest/` → `digests/`.
- Removed the "Only" field from both UIs (`--only` remains on the CLI). Title matching ignores accents.

### Section folders, GUI and TUI (`5df73f4`) — breaking
- Downloads go to a user-named section folder outside the tool (`cases/`, `digest/`, `report.csv`, `cases.yaml`).
- Added `gui.py` (CustomTkinter) and `tui.py` (rich); last choices remembered in `settings.json`.
- Every not-found case gets a reason in `report.csv`; the prof's notes are carried into it; the report
  is merged across runs.
- CLI now requires `--dest`; `--out` and the default `downloads/` folder are gone.

### First version (`e09857a`)
- `cdasia_fetch.py`: CDAsia downloader via Playwright with a persistent OpenAthens login, searching by
  citation / G.R. No. and including all separate opinions.
