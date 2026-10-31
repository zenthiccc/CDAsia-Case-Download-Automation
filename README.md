# CDAsia case downloader

This folder is the automation tool. Downloads go into a **section folder** that you name and place
anywhere outside it:

```
<anywhere>/<section name>/
  cases/        downloaded PDFs, numbered in syllabus order, including all separate opinions
  digest/       for your digests
  report.csv    matched case, G.R. No., date, opinions included, and the prof's note
  cases.yaml    copy of the syllabus yaml the folder was built from
```

## Run
```
.venv/bin/python gui.py     # desktop window
.venv/bin/python tui.py     # terminal prompts
```
Both ask for a syllabus yaml (from `syllabi/` or anywhere), where to create the folder, its name, and
optionally a filter to download only some cases. They remember your last choices (`settings.json`).
Without a UI:
```
.venv/bin/python cdasia_fetch.py --cases syllabi/x.yaml --dest ~/Downloads/x [--only Ocampo]
```
A Chromium window opens. If you're off campus and not logged in, sign in through OpenAthens in that
window; the script continues on its own once the CDAsia search page appears. The login is kept in
`.cdasia_profile/`. Rerunning into the same folder skips cases already in `cases/`.

## New syllabus
Put the syllabus text in `syllabi/<name>.md` and make `syllabi/<name>.yaml` like the existing one. For
each case give a `name`, a `citation` and/or `gr` (G.R. No.), `match` (a word from the case title),
optionally `year`, and optionally `note` (the prof's note in parentheses after the case in the
syllabus; it's copied into `report.csv`). The script searches by citation first, falls back to
G.R. No., and picks the result whose title contains a `match` word (and the year).

## When a case can't be found
The script never stops on a missing case; it logs it and moves on. `report.csv` says why:
- **no result title matched `match`; CDAsia returned: ...**: CDAsia has something for that citation/G.R. No.
  but the title didn't contain your `match` word. If one of the listed titles is the right case, fix `match`
  and rerun with `--only`.
- **CDAsia has no results for the citation or G.R. No.**: check the citation/G.R. No. against the syllabus
  (typos are common), else the case isn't on CDAsia; get it elsewhere (e.g. the SC E-Library / LawPhil).
- **search timed out**: site was slow or the login expired; just rerun.
- **check: N matches, took first**: it downloaded something, but open the PDF to confirm it's the right one.

## First-time setup (already done on this Mac)
```
brew install python-tk@3.13      # Tk for the desktop window
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/playwright install chromium
```
