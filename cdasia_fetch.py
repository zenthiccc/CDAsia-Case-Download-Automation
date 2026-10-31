"""Download case PDFs (with separate opinions) from CDAsia for every case in a cases.yaml.

Usage:
  .venv/bin/python cdasia_fetch.py                 # all cases in cases.yaml
  .venv/bin/python cdasia_fetch.py --only Flores   # just the cases whose name contains "Flores"
  .venv/bin/python cdasia_fetch.py --cases other.yaml --out other_folder
"""
import argparse
import csv
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

import yaml
from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
BASE = "https://cdasiaonline-com.ap2.proxy.openathens.net"
PROFILE = HERE / ".cdasia_profile"
DELAY_S = 4  # pause between cases, to go easy on the site


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
    """Run a search and return the result rows as (row_handle, ref, title, date)."""
    page.goto(search_url(**query))
    try:
        page.wait_for_function(
            "document.querySelector('tbody tr') || /no (results|documents)|0 document/i.test(document.body.innerText)",
            timeout=30000)
    except PWTimeout:
        return []
    page.wait_for_timeout(1000)
    rows = []
    for r in page.query_selector_all("tbody tr"):
        cells = [c.inner_text().strip() for c in r.query_selector_all("td")]
        if len(cells) >= 3:
            rows.append((r, cells[0], cells[1], cells[2]))
    return rows


def pick(rows, case):
    """Choose the result row that matches the case's title keywords (and year, if given)."""
    keys = [k.lower() for k in case.get("match", [])]
    hits = [r for r in rows if any(k in r[2].lower() for k in keys)] if keys else rows
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default=str(HERE / "cases.yaml"))
    ap.add_argument("--out", default=str(HERE / "downloads"))
    ap.add_argument("--only", help="only cases whose name contains this text")
    args = ap.parse_args()

    cases = yaml.safe_load(Path(args.cases).read_text())
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    report_path = out / "report.csv"

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
            dest = out / f"{i:02d} - {safe_filename(name)}.pdf"
            rec = {"no": i, "case": name, "status": "", "matched": "", "ref": "", "date": "",
                   "opinions": "", "file": dest.name}
            if dest.exists():
                print(f"[{i:02d}] {name}: already downloaded, skipping")
                rec["status"] = "skipped (exists)"
                results.append(rec)
                continue

            hits = []
            for field, key in (("citation", "citation"), ("number", "gr")):
                if case.get(key):
                    hits = pick(search(page, **{field: case[key]}), case)
                    if hits:
                        break
            if not hits:
                print(f"[{i:02d}] {name}: NOT FOUND")
                rec["status"] = "not found"
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

    with report_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0].keys()) if results else ["case"])
        w.writeheader()
        w.writerows(results)
    bad = [r for r in results if not r["status"].endswith("ok") and not r["status"].startswith("skipped")]
    print(f"\nDone. {len(results) - len(bad)} ok/skipped, {len(bad)} need attention. Report: {report_path}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
