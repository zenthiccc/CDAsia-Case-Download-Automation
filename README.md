# CDAsia case downloader

This folder is the automation tool. Downloads go into a **section folder** that you name and place
anywhere outside it:

```
<anywhere>/<section name>/
  cases/          downloaded PDFs, numbered in syllabus order, including all separate opinions
  digests/        for your digests
  cases.yaml      the case list, generated from the syllabus and checked by you
  syllabus.md     the syllabus you gave it
  PROMPT.md, SAMPLE-DIGEST-STYLE-TO-FOLLOW.md   copied from this folder, for writing the digests
  report.csv      matched case, G.R. No., date, opinions included, and the prof's note
```

## Run
```
.venv/bin/python gui.py     # desktop window
.venv/bin/python tui.py     # terminal prompts
```
1. Pick the syllabus: paste the part of the PDF syllabus you need into a `.md` file (in `syllabi/` it shows
   up in the list; anywhere else, browse to it).
2. Choose where to create the folder and name it.
3. Check the case list. Each line with a citation (`156 SCRA 549`, `50 PHIL 259`) or a G.R. No. becomes a
   case; the text in parentheses becomes its `note`; headings stay as `#` comments. Fix what the
   syllabus got wrong (typo'd pages, missing names), edit `match` words if needed. `# CHECK:` marks
   guesses, e.g. a citation with no "SCRA". The GUI edits it in place; the TUI opens your `$EDITOR`.
4. Download. A Chromium window opens. If you're off campus and not logged in, sign in through
   OpenAthens in that window; the script continues on its own once the CDAsia search page appears. The
   login is kept in `.cdasia_profile/`.

Rerunning into the same folder reuses your checked `cases.yaml` and skips cases already in `cases/`.
Without a UI:
```
.venv/bin/python cdasia_fetch.py --syllabus syllabi/x.md --dest ~/Downloads/x [--only Ocampo]
```

## The case list (`cases.yaml`)
Per case: `name`, `citation` and/or `gr` (G.R. No.), `match` (words, any one of which must be in
CDAsia's title), optionally `year` and `note`. The script searches by citation first, falls back to
G.R. No., and picks the result whose title contains a `match` word (and the year). Adding a `gr` gives
a citation-only case a fallback if the citation is wrong.

## When a case can't be found
The script never stops on a missing case; it logs it and moves on. `report.csv` says why:
- **no result title matched `match`; CDAsia returned: ...**: CDAsia has something for that citation/G.R. No.
  but the title didn't contain your `match` word. If one of the listed titles is the right case, fix `match`
  and download again (finished cases are skipped).
- **CDAsia has no results for the citation or G.R. No.**: check the citation/G.R. No. against the syllabus
  (typos are common), else the case isn't on CDAsia; get it elsewhere (e.g. the SC E-Library / LawPhil).
- **search timed out**: site was slow or the login expired; just rerun.
- **check: N matches, took first**: it downloaded something, but open the PDF to confirm it's the right one.

## First-time setup (already done on this Mac)
```
brew install python-tk@3.13      # Tk for the desktop window
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/playwright install chromium
```
