# Plan

Where the project stands and what could come next. Design details are in [ARCHITECTURE.md](ARCHITECTURE.md).

## Goal

Stop downloading syllabus cases from CDAsia by hand. Paste the relevant part of the syllabus, check the
case list, and get every case (with all separate opinions) in a named section folder, ready for the
digest step described in `PROMPT.md`.

## Done

- [x] Engine: persistent login through OpenAthens, search by citation then G.R. No., title/year matching,
      download with all separate opinions, skip existing files, polite delay.
- [x] `report.csv` with a reason for every case that isn't downloaded; merged across runs.
- [x] Per-run section folders outside the tool folder, named by the user.
- [x] Desktop GUI (CustomTkinter) and terminal UI (rich).
- [x] Syllabus `.md` as the input: case list generated automatically, reviewed/edited before download.
- [x] Section folders include `syllabus.md`, `PROMPT.md`, `SAMPLE-DIGEST-STYLE-TO-FOLLOW.md`, `digests/`.
- [x] First section done: Art. VII Secs. 16–17, 19/19 cases (the `example-*` files in `syllabi/`).
- [x] Prepared for publishing: configurable `CDASIA_URL`, `templates/`, local-only syllabi, screenshots,
      MIT license, home paths shown as `~`.

## Known limitations

- The parser copies syllabus typos (wrong page numbers, misspelled names, missing "SCRA"); they're only
  caught at review time or as "no results" in the report.
- Citation-only cases have no fallback if the citation is wrong; the parser can't look up G.R. Nos.
- Broad `match` words (e.g. *Lim*, *Torres*) can match a different case on the same SCRA page; the report
  flags these as `check: N matches`.
- Lines whose case name wraps *before* the citation, or headings that start in lowercase, can be
  mis-joined by the parser.
- Selectors depend on CDAsia's current UI; a site redesign breaks `download_case()`.
- Only tested on macOS. Windows/Linux paths exist (`os.startfile`/`xdg-open`, fonts) but are untested.
- No automated tests; the parser is the easiest place to add them (syllabus text in, yaml out).

## Ideas (not started)

- In the review step, a "check citations" action that searches each case on CDAsia and shows what it
  would match, before committing to the full download.
- Fill in missing G.R. Nos. from the first successful citation search and save them to `cases.yaml`.
- Kick off the digest step from the UI once downloads finish.
- Retry only failed cases from the report.

## Original approach (2026-10-31)

The first plan was a Playwright script with a hand-written `cases.yaml`, built after recording CDAsia's
DOM in a live session (search box, results table, download button, separate-opinions dialog). Verification
was: one case (`--only Flores`), the full list with spot checks (Ang-Angco, Ocampo), then a rerun to
confirm everything is skipped. All three passed. The yaml-by-hand step was later replaced by the parser.

Check that the school's CDAsia license allows automated downloads for personal use; the tool runs
slowly and only fetches assigned cases.
