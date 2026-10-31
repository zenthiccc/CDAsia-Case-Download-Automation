"""Download case PDFs (with separate opinions) from CDAsia for every case in a syllabus.

Each run fills a "section folder" that lives outside this project:
  <section>/cases/      the downloaded PDFs
  <section>/digests/    for your digests
  <section>/cases.yaml  the case list (generated from the syllabus, then checked/edited)
  <section>/syllabus.md, PROMPT.md, SAMPLE-DIGEST-STYLE-TO-FOLLOW.md, report.csv

Usage (or use gui.py / tui.py, which let you review the generated yaml first):
  .venv/bin/python cdasia_fetch.py --syllabus syllabi/x.md --dest ~/Downloads/x
  .venv/bin/python cdasia_fetch.py --cases my.yaml --dest ~/Downloads/x --only Flores
"""
import argparse
import csv
import json
import os
import unicodedata
import re
import shutil
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

import syllabus_parser

HERE = Path(__file__).resolve().parent
# CDAsia through the school's OpenAthens proxy. For another institution's proxy (or direct access),
# set CDASIA_URL, e.g. CDASIA_URL=https://cdasiaonline.com
BASE = os.environ.get("CDASIA_URL", "https://cdasiaonline-com.ap2.proxy.openathens.net").rstrip("/")
PROFILE = HERE / ".cdasia_profile"
SYLLABI = HERE / "syllabi"
SETTINGS = HERE / "settings.json"  # remembers the UIs' last choices
DELAY_S = 4  # pause between cases, to go easy on the site
TEMPLATES = HERE / "templates"  # copied into every section folder, for writing the digests
DIGEST_FILES = ("PROMPT.md", "SAMPLE-DIGEST-STYLE-TO-FOLLOW.md")


def shown(path):
    """A path for printing, with the home folder as ~."""
    path, home = Path(path), Path.home()
    return f"~/{path.relative_to(home)}" if path.is_relative_to(home) else str(path)


def load_settings():
    try:
        return json.loads(SETTINGS.read_text())
    except (OSError, ValueError):
        return {}


def save_settings(**values):
    SETTINGS.write_text(json.dumps({**load_settings(), **values}, indent=2))


def prepare_section(dest, cases_text, syllabus=None):
    """Create the section folder layout and write its cases.yaml, syllabus.md and digest files."""
    dest = Path(dest).expanduser()
    for sub in ("cases", "digests"):
        (dest / sub).mkdir(parents=True, exist_ok=True)
    (dest / "cases.yaml").write_text(cases_text)
    if syllabus and Path(syllabus).resolve() != (dest / "syllabus.md").resolve():
        shutil.copyfile(syllabus, dest / "syllabus.md")
    for name in DIGEST_FILES:
        # Don't overwrite: the section's copy may have been tailored.
        if (TEMPLATES / name).exists() and not (dest / name).exists():
            shutil.copyfile(TEMPLATES / name, dest / name)
    return dest


def draft_cases(syllabus, dest):
    """The yaml to review for a syllabus: the folder's saved cases.yaml if it was made from this same
    syllabus (keeps your edits), else a fresh parse. Returns (text, came_from_folder)."""
    syllabus, dest = Path(syllabus), Path(dest).expanduser()
    text = syllabus.read_text()
    saved, copy = dest / "cases.yaml", dest / "syllabus.md"
    if saved.exists() and copy.exists() and copy.read_text() == text:
        return saved.read_text(), True
    return syllabus_parser.to_yaml(text, syllabus.name), False


def search_url(**query):
    params = {"result": "true", **query, "library": "All", "perPage": "50", "page": "1",
              "sortByReferenceNo": "default", "sortByDate": "default"}
    return f"{BASE}/?{urlencode(params)}"


def safe_filename(s):
    return re.sub(r'[\\/:*?"<>|]+', "", s).strip()


def ensure_logged_in(page):
    page.goto(BASE + "/")
    try:
        page.wait_for_selector("#input-Number", timeout=15000)
        return
    except PWTimeout:
        pass
    print("\n>>> Please log in to CDAsia in the browser window (OpenAthens / school account).")
    print(">>> Waiting until the CDAsia search page appears...")
    page.wait_for_selector("#input-Number", timeout=10 * 60 * 1000)
    print(">>> Logged in.\n")


def search(page, **query):
    """Run a search and return the result rows as (row_handle, ref, title, date), or None on timeout."""
    page.goto(search_url(**query))
    try:
        page.wait_for_function(
            "document.querySelector('tbody tr') || /no (results|documents)|0 document/i.test(document.body.innerText)",
            timeout=30000)
    except PWTimeout:
        return None
    page.wait_for_timeout(1000)
    rows = []
    for r in page.query_selector_all("tbody tr"):
        cells = [c.inner_text().strip() for c in r.query_selector_all("td")]
        if len(cells) >= 3:
            rows.append((r, cells[0], cells[1], cells[2]))
    return rows


def fold(s):
    """Lowercase without accents, so "Pano" matches "Paño"."""
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


def pick(rows, case):
    """Choose the result row that matches the case's title keywords (and year, if given)."""
    keys = [fold(k) for k in case.get("match", [])]
    hits = [r for r in rows if any(k in fold(r[2]) for k in keys)] if keys else rows
    if case.get("year"):
        by_year = [r for r in hits if str(case["year"]) in r[3]]
        hits = by_year or hits
    # Prefer the main decision over later resolutions on the same case.
    main = [r for r in hits if "resolution" not in r[1].lower()]
    hits = main or hits
    return hits


def download_case(ctx, page, row, dest):
    """Open a result row and save its PDF (with all separate opinions) to dest."""
    with ctx.expect_page() as new_page:
        row.click()
    doc = new_page.value
    try:
        doc.wait_for_selector("[aria-label=download-button]", timeout=60000)
        doc.wait_for_timeout(2000)
        downloads = []
        doc.on("download", lambda d: downloads.append(d))
        doc.click("[aria-label=download-button]")

        # CDAsia either starts the download directly (no separate opinions) or first shows
        # an "Include Separate Opinions" dialog. Wait for whichever comes first.
        dialog = doc.locator(".MuiDialog-root:visible")
        opinions = []
        deadline = time.time() + 180
        while not downloads and time.time() < deadline:
            if dialog.count():
                # The opinion list loads after the dialog appears; wait until it stops growing.
                boxes, last, stable = dialog.locator("input[type=checkbox]"), -1, 0
                for _ in range(40):
                    n = boxes.count()
                    stable = stable + 1 if n == last and n > 1 else 0
                    if stable >= 3:
                        break
                    last = n
                    doc.wait_for_timeout(500)
                rows = dialog.locator("tbody tr").all_inner_texts()[1:]  # skip "Select All"
                opinions = [" ".join(r.split()) for r in rows]
                dialog.locator("#select-all-cb").check()
                doc.wait_for_timeout(300)
                if dialog.locator("input[type=checkbox]:checked").count() != boxes.count():
                    raise RuntimeError("could not select all separate opinions")
                with doc.expect_download(timeout=180000) as dl:
                    dialog.get_by_role("button", name="Add Selected Opinions").click()
                downloads.append(dl.value)
                break
            doc.wait_for_timeout(500)
        if not downloads:
            raise RuntimeError("download did not start")
        downloads[0].save_as(dest)
        return opinions
    finally:
        doc.close()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", required=True, help="section folder to fill (created if missing)")
    ap.add_argument("--syllabus", help="syllabus .md; copied into the folder, and parsed if there's no yaml")
    ap.add_argument("--cases", help="cases yaml (default: <dest>/cases.yaml, else generated from --syllabus)")
    ap.add_argument("--only", help="only cases whose name contains this text")
    args = ap.parse_args(argv)

    existing = Path(args.dest).expanduser() / "cases.yaml"
    if args.cases:
        text = Path(args.cases).read_text()
    elif existing.exists():
        text = existing.read_text()
    elif args.syllabus:
        text = syllabus_parser.to_yaml(Path(args.syllabus).read_text(), Path(args.syllabus).name)
    else:
        ap.error("give --syllabus or --cases")
    try:
        cases = syllabus_parser.validate(text)
    except ValueError as e:
        ap.error(f"cases yaml: {e}")
    out = prepare_section(args.dest, text, args.syllabus)
    cases_dir = out / "cases"
    report_path = out / "report.csv"
    print(f"Section folder: {shown(out)}", flush=True)
    # Keep match/opinion details of already-downloaded cases from the last run's report.
    previous = {}
    if report_path.exists():
        with report_path.open(newline="") as f:
            previous = {r["file"]: r for r in csv.DictReader(f)}

    results = []
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(str(PROFILE), headless=False, accept_downloads=True,
                                                   viewport={"width": 1400, "height": 900})
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        ensure_logged_in(page)

        for i, case in enumerate(cases, 1):
            name = case["name"]
            if args.only and args.only.lower() not in name.lower():
                continue
            dest = cases_dir / f"{i:02d} - {safe_filename(name)}.pdf"
            rec = {"no": i, "case": name, "note": case.get("note", ""), "status": "", "matched": "", "ref": "", "date": "",
                   "opinions": "", "file": dest.name}
            if dest.exists():
                print(f"[{i:02d}] {name}: already downloaded, skipping")
                old = previous.get(dest.name, {})
                rec.update({k: old.get(k, "") for k in ("matched", "ref", "date", "opinions")})
                rec["status"] = "skipped (exists)"
                results.append(rec)
                continue

            hits, seen, timed_out = [], [], False
            for field, key in (("citation", "citation"), ("number", "gr")):
                if case.get(key):
                    rows = search(page, **{field: case[key]})
                    if rows is None:
                        timed_out = True
                        continue
                    seen += [f"{r[2]} ({r[1]}, {r[3]})" for r in rows[:3]]
                    hits = pick(rows, case)
                    if hits:
                        break
            if not hits:
                # Say *why* so the fix is obvious: wrong `match` word, CDAsia lacks it, or the site hung.
                if seen:
                    rec["status"] = "not found: no result title matched `match`; CDAsia returned: " + "; ".join(seen)
                elif timed_out:
                    rec["status"] = "not found: search timed out (site slow, or logged out?) - rerun"
                elif not (case.get("citation") or case.get("gr")):
                    rec["status"] = "not found: no citation or gr in the yaml"
                else:
                    rec["status"] = "not found: CDAsia has no results for the citation or G.R. No. - download manually"
                print(f"[{i:02d}] {name}: {rec['status']}")
                results.append(rec)
                continue

            row, ref, title, date = hits[0]
            rec.update(matched=title, ref=ref, date=date)
            if len(hits) > 1:
                rec["status"] = f"check: {len(hits)} matches, took first; "
            print(f"[{i:02d}] {name}: {title} ({ref}, {date}) ... ", end="", flush=True)
            try:
                opinions = download_case(ctx, page, row, dest)
                rec["opinions"] = "; ".join(opinions)
                rec["status"] += "ok"
                print(f"saved ({len(opinions)} separate opinion(s) included)")
            except Exception as e:
                rec["status"] += f"error: {e}".splitlines()[0][:200]
                print("FAILED:", rec["status"])
            results.append(rec)
            time.sleep(DELAY_S)

        ctx.close()

    # Merge into the existing report so `--only` runs don't drop the other cases.
    merged = {**previous, **{r["file"]: r for r in results}}
    with report_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0].keys()) if results else ["case"],
                           restval="", extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(merged.values(), key=lambda r: int(r["no"])))
    bad = [r for r in results if not r["status"].endswith("ok") and not r["status"].startswith("skipped")]
    print(f"\nDone. {len(results) - len(bad)} ok/skipped, {len(bad)} need attention. Report: {shown(report_path)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
