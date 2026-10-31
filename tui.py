"""Terminal UI for the CDAsia downloader: pick a syllabus yaml, name the section folder, download.

  .venv/bin/python tui.py
"""
import csv
from pathlib import Path

import yaml
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table

import cdasia_fetch as engine

console = Console()


def choose_yaml():
    files = sorted(engine.SYLLABI.glob("*.y*ml"))
    table = Table(title="Syllabi", title_justify="left", show_edge=False)
    table.add_column("#", style="cyan", justify="right")
    table.add_column("file")
    table.add_column("cases", justify="right", style="dim")
    for i, f in enumerate(files, 1):
        table.add_row(str(i), f.name, str(len(yaml.safe_load(f.read_text()) or [])))
    table.add_row("0", "[italic]another file...[/]", "")
    console.print(table)
    n = IntPrompt.ask("Syllabus", choices=[str(i) for i in range(len(files) + 1)],
                      default=1 if files else 0, show_choices=False)
    if n:
        return files[n - 1]
    while True:
        p = Path(Prompt.ask("Path to yaml").strip().strip("'\"")).expanduser()
        if p.is_file():
            return p
        console.print(f"[red]No such file:[/] {p}")


def show_report(report):
    if not report.exists():
        return
    table = Table(show_edge=False)
    for col in ("#", "case", "status", "opinions"):
        table.add_column(col, overflow="fold")
    with report.open(newline="") as f:
        for r in csv.DictReader(f):
            ok = r["status"].endswith("ok") or r["status"].startswith("skipped")
            style = "green" if ok else "red"
            opinions = str(len(r["opinions"].split("; "))) if r["opinions"] else ""
            table.add_row(r["no"], r["case"], f"[{style}]{r['status']}[/]", opinions)
    console.print(table)


def main():
    console.print(Panel.fit("[bold]CDAsia Case Downloader[/]\nCases with separate opinions → <folder>/cases",
                            border_style="cyan"))
    settings = engine.load_settings()

    cases_yaml = choose_yaml()
    parent = Path(Prompt.ask("Create the folder in",
                             default=settings.get("parent", str(engine.HERE.parent)))).expanduser()
    name = ""
    while not name:
        name = engine.safe_filename(Prompt.ask("Folder name", default=cases_yaml.stem))
    only = Prompt.ask("Only cases containing (blank = all)", default="").strip()
    dest = parent / name

    console.print(f"\n  syllabus  [cyan]{cases_yaml}[/]\n  folder    [cyan]{dest}[/]  (cases/, digest/)"
                  + (f"\n  only      [cyan]{only}[/]" if only else ""))
    if not Confirm.ask("Start downloading?", default=True):
        return
    engine.save_settings(parent=str(parent), yaml=str(cases_yaml))

    argv = ["--cases", str(cases_yaml), "--dest", str(dest)] + (["--only", only] if only else [])
    code = engine.main(argv)
    console.rule("Report")
    show_report(dest / "report.csv")
    console.print(f"[dim]Open the folder with:[/] open '{dest}'")
    return code


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopped.[/]")
