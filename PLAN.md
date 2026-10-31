# Plan: Automate CDAsia case downloads from syllabus

## Context
Right now the user downloads each case in `syllabus.md` (Art. VII Secs. 16–17) by hand from CDAsia (`https://cdasiaonline-com.ap2.proxy.openathens.net/`, behind the school's OpenAthens login), searching by G.R. No. or citation and taking the PDF that includes separate opinions when one exists. The goal is a reusable Python + Playwright script: the user logs in once, then the script downloads every case on a list. It should also work for later syllabi.

## Files to create (in `/Users/djesph/Downloads/consti-art7-sec16-sec17/`)
- `cases.yaml`: the case list pulled from `syllabus.md`. Each entry has a short name, the citation as written, and a G.R. No. where I'm confident of it. A `verify: true` flag marks the uncertain ones (e.g. Springer, 50 Phil 259; the Pobre citation "224 738", which is missing its "SCRA"). Non-case items such as the Bernas Commentary and "Aquino appointments" are left out.
- `cdasia_fetch.py`: the downloader.
- `parse_syllabus.py` (small helper): reads a syllabus `.md`, uses regexes to pull out `G.R. No. …`, `### SCRA ###` and `## PHIL ###` citations, and writes a draft `cases.yaml` for future syllabi. The user checks the draft before running.
- `README.md`: a short how-to (install, first login, run).

## How `cdasia_fetch.py` works
1. **Persistent login:** uses `playwright.chromium.launch_persistent_context("./.cdasia_profile", headless=False)`. On the first run it opens the CDAsia URL and waits for the user to finish the OpenAthens/SSO login (it detects a logged-in element or the user presses Enter). Later runs reuse the saved session.
2. **Per case:** search by G.R. No. first, then fall back to the citation. Open the matching decision, choosing the result whose title or date matches when there are several. Use the version with separate opinions if CDAsia offers one. Then trigger the PDF download with `page.expect_download()`, or use print-to-PDF via `page.pdf()` in a headless context with the same cookies if CDAsia only offers a print view.
3. **Output:** `downloads/<NN>_<Short Name>_<GR or citation>.pdf`, numbered in syllabus order. Cases already downloaded are skipped, so a rerun picks up where it stopped.
4. **Robustness:** a polite delay of a few seconds between cases (we're downloading ~19 cases for personal study, not crawling the site). Each failure is logged to `report.csv` (case, status, matched title, file) and the script moves on. `--only "Flores"` re-runs a single case and `--debug` saves a screenshot when something fails.

## Step 0 (needed before writing selectors): learn the site's structure
I don't know CDAsia's DOM, so the selectors can't be written blind. Once the plan is approved, I'll run a small Playwright session (headed, using the same persistent profile). You log in, then I record the search box, the result list, the separate-opinions toggle and the download/print controls on one or two sample cases (e.g. G.R. No. 104732, Flores v. Drilon). The selectors in `cdasia_fetch.py` will come from what I record there.

## Setup
`python3 -m venv .venv && .venv/bin/pip install playwright pyyaml && .venv/bin/playwright install chromium`

## Verification
1. Run `--only "Flores"`: check that the PDF opens, that it's the right case, and that it includes the separate opinions if any exist.
2. Run the full list and check `report.csv` for any not-found or wrong matches. Spot-check one older case (Ang-Angco, 9 SCRA 619) and one recent case (Ocampo v. Enriquez, G.R. 225973).
3. Run it again and confirm everything is skipped (idempotent).

## Note
Check that your school's CDAsia license allows automated downloads for personal use. The script runs slowly and only downloads your own assigned cases, which keeps the risk low.
