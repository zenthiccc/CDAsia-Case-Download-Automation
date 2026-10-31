# CDAsia case downloader

Downloads every case in `cases.yaml` from CDAsia as a PDF, **including all separate opinions**
(concurring/dissenting) when CDAsia has them. Files land in `downloads/` numbered in syllabus order,
with a `downloads/report.csv` listing the matched case, G.R. No., date and which opinions were included.

## Run
```
.venv/bin/python cdasia_fetch.py                 # all cases (already-downloaded ones are skipped)
.venv/bin/python cdasia_fetch.py --only Ocampo   # one case
.venv/bin/python cdasia_fetch.py --cases next_week.yaml --out next_week
```
A Chromium window opens. If you're off campus and not logged in, sign in through OpenAthens in that
window; the script continues on its own once the CDAsia search page appears. The login is kept in
`.cdasia_profile/`.

## New syllabus
Make a new `.yaml` like `cases.yaml`: for each case give a `name`, a `citation` and/or `gr` (G.R. No.),
`match` (a word from the case title) and optionally `year`. The script searches by citation first,
falls back to G.R. No., and picks the result whose title contains a `match` word (and the year).
Check `report.csv` for anything marked "not found" or "check".

## First-time setup (already done on this Mac)
```
python3 -m venv .venv && .venv/bin/pip install playwright pyyaml && .venv/bin/playwright install chromium
```
