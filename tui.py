"""Terminal UI for the CDAsia downloader: pick a syllabus .md, name the section folder, check the
generated case list, download.

  .venv/bin/python tui.py
"""
import csv
import os
import shlex
import subprocess
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.syntax import Syntax
from rich.table import Table

import cdasia_fetch as engine
import syllabus_parser

console = Console()


def choose_syllabus():
    files = sorted(engine.SYLLABI.glob("*.md"))
    table = Table(title="Syllabi", title_justify="left", show_edge=False)
    table.add_column("#", style="cyan", justify="right")
    table.add_column("file")
    for i, f in enumerate(files, 1):
        table.add_row(str(i), f.name)
    table.add_row("0", "[italic]another file...[/]")
    console.print(table)
    n = IntPrompt.ask("Syllabus", choices=[str(i) for i in range(len(files) + 1)],
                      default=1 if files else 0, show_choices=False)
    if n:
        return files[n - 1]
    while True:
        p = Path(Prompt.ask("Path to syllabus .md").strip().strip("'\"")).expanduser()
        if p.is_file():
            return p
        console.print(f"[red]No such file:[/] {p}")


def show_cases(path):
    """Print the yaml and a summary table; return the case list, or None if it doesn't validate."""
    text = path.read_text()
    console.print(Syntax(text, "yaml", line_numbers=True, word_wrap=True))
    try:
        cases = syllabus_parser.validate(text)
    except ValueError as e:
        console.print(f"[red]✗ {e}[/]")
        return None
    table = Table(show_edge=False)
    for col in ("#", "case", "citation", "G.R. No.", "match"):
        table.add_column(col, overflow="fold")
    for i, c in enumerate(cases, 1):
        table.add_row(str(i), c["name"], c.get("citation", ""), str(c.get("gr", "")), ", ".join(c.get("match", [])))
    console.print(table)
    checks = text.count("# CHECK:")
    console.print(f"[green]✓ {len(cases)} cases.[/]" + (f" [yellow]{checks} line(s) marked # CHECK.[/]" if checks else ""))
    return cases


def edit(path):
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "nano"
    subprocess.run([*shlex.split(editor), str(path)])


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
    console.print(Panel.fit("[bold]CDAsia Case Downloader[/]\nSyllabus → case list to check → <folder>/cases",
                            border_style="cyan"))
    settings = engine.load_settings()

    syllabus = choose_syllabus()
    parent = Path(Prompt.ask("Create the folder in",
                             default=settings.get("parent", str(engine.HERE.parent)))).expanduser()
    name = ""
    while not name:
        name = engine.safe_filename(Prompt.ask("Folder name", default=syllabus.stem))
    dest = parent / name

    text, saved = engine.draft_cases(syllabus, dest)
    engine.prepare_section(dest, text, syllabus)
    yaml_path = dest / "cases.yaml"
    console.rule("Cases to download")
    if saved:
        console.print(f"[dim]Using the cases.yaml already in {dest} (your earlier edits).[/]")
    while True:
        cases = show_cases(yaml_path)
        choices = ["d", "e", "r", "q"] if cases else ["e", "r", "q"]
        action = Prompt.ask(r"\[d]ownload, \[e]dit the list, \[r]egenerate from syllabus, \[q]uit"
                            if cases else r"Fix it: \[e]dit, \[r]egenerate from syllabus, \[q]uit",
                            choices=choices, default=choices[0], show_choices=False)
        if action == "e":
            edit(yaml_path)
        elif action == "r":
            if Confirm.ask("Discard your edits and regenerate?", default=False):
                yaml_path.write_text(syllabus_parser.to_yaml(syllabus.read_text(), syllabus.name))
        elif action == "q":
            console.print(f"[dim]The list is saved in {yaml_path}; run again to continue.[/]")
            return
        else:
            break

    engine.save_settings(parent=str(parent), syllabus=str(syllabus))
    code = engine.main(["--dest", str(dest), "--cases", str(yaml_path), "--syllabus", str(syllabus)])
    console.rule("Report")
    show_report(dest / "report.csv")
    console.print(f"[dim]Open the folder with:[/] open '{dest}'")
    return code


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopped.[/]")
