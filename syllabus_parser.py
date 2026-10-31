"""Turn syllabus text (copy-pasted from the PDF) into a draft cases yaml.

  .venv/bin/python syllabus_parser.py syllabi/x.md > x.yaml

A case is any line with a reporter citation (`158 SCRA 549`, `50 PHIL 259`) or a G.R. No.; headings
and other lines without one are kept only as yaml comments. The draft is meant to be checked: the
syllabus' own typos (wrong page, missing "SCRA") come through as written.
"""
import json
import re
import sys
from pathlib import Path

CITATION = re.compile(r"\b(\d{1,4})\s+(SCRA|PHIL\.?|Phil\.?|OG|O\.G\.)\s+(\d{1,5})\b")
BARE_CITATION = re.compile(r"\b(\d{1,4})\s+(\d{1,5})\s*(?=\[\d{4}\])")  # "224 738 [1993]": reporter left out
GR = re.compile(r"\bG\.?\s*R\.?\s*Nos?\.?\s*(L-\s*)?(\d[\d-]*)", re.I)
BRACKET_YEAR = re.compile(r"\[(\d{4})\]")
DATE_YEAR = re.compile(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},\s*(\d{4})")
BULLET = re.compile(r"^\s*(?:[•●▪◦·*]|-(?=\s)|\d+[.)](?=\s))\s*")
OPTIONAL = re.compile(r"^\s*OPTIONAL\s*:\s*", re.I)
# Words that don't identify a case title, so they're never used as `match` words.
STOP = {"the", "of", "and", "for", "in", "on", "et", "al", "inc", "corp", "co", "vs", "people", "republic",
        "government", "philippines", "philippine", "islands", "ca", "op", "comelec", "court", "appeals",
        "dir", "gen", "sec", "hon", "jr", "sr", "ii", "iii", "iv", "national", "executive", "secretary", "office", "president"}


def has_case(line):
    return bool(CITATION.search(line) or BARE_CITATION.search(line) or GR.search(line))


def logical_lines(text):
    """Join the PDF's wrapped lines back onto the case they belong to.

    A line continues the previous case while that case's note is still open (more "(" than ")") and
    the line starts in lowercase or with punctuation, as wrapped notes do; headings start in uppercase.
    """
    out = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if (out and has_case(out[-1]) and out[-1].count("(") > out[-1].count(")")
                and not BULLET.match(line) and not has_case(line) and not line[0].isupper()):
            out[-1] += " " + line
        else:
            out.append(line)
    return out


def match_words(name):
    words = []
    for party in re.split(r"\s+v(?:s)?\.?\s+", name, maxsplit=1):
        for w in re.split(r"[\s\-–.,()]+", party):
            if len(w) >= 3 and w.isalpha() and w.lower() not in STOP and w not in words:
                words.append(w)
    return words[:4] or [name.split()[0]]


def parse_case(line):
    line = BULLET.sub("", line)
    optional = bool(OPTIONAL.match(line))
    line = OPTIONAL.sub("", line)
    case, checks = {}, []

    cite = CITATION.search(line)
    gr = GR.search(line)
    bare = None if cite else BARE_CITATION.search(line)
    if cite:
        reporter = "SCRA" if cite[2] == "SCRA" else "Phil" if cite[2].lower().startswith("phil") else "O.G."
        case["citation"] = f"{cite[1]} {reporter} {cite[3]}"
    elif bare:
        case["citation"] = f"{bare[1]} SCRA {bare[2]}"
        checks.append(f"syllabus says \"{bare[0].strip()}\"; assumed SCRA")
    if gr:
        case["gr"] = (gr[1] or "").replace(" ", "") + gr[2]

    starts = [m.start() for m in (cite, bare, gr) if m]
    name = line[:min(starts)]
    rest = line[min(starts):]
    name = re.sub(r"\s*[–—-]\s*", "-", name.strip()).strip(" -,:")  # "Velicaria – Grafel" -> "Velicaria-Grafel"
    name = re.sub(r"\s+", " ", name)
    case = {"name": name + (" (OPTIONAL)" if optional else ""), **case}

    note = re.search(r"\((.*)", rest)
    if note:
        text = note[1].strip()
        if text.endswith(")") and text.count("(") < text.count(")"):
            text = text[:-1]
        case["note"] = text.strip()

    case["match"] = match_words(name)
    year = BRACKET_YEAR.search(rest) or DATE_YEAR.search(rest)
    if year:
        case["year"] = int(year[1])
    return case, checks


def parse(text):
    """Return [(kind, value)]: ("heading", text) for lines without a case, ("case", (dict, checks)) for cases."""
    items = []
    for line in logical_lines(text):
        if has_case(line):
            items.append(("case", parse_case(line)))
        else:
            items.append(("heading", line))
    return items


def q(s):
    return json.dumps(s, ensure_ascii=False)  # a JSON string is a valid YAML string


def to_yaml(text, source="syllabus"):
    items = parse(text)
    n = sum(kind == "case" for kind, _ in items)
    lines = [f"# Cases from {source} ({n} found), in syllabus order. Check and edit before downloading.",
             "# Each case is searched by `citation` first, then by `gr` (G.R. No.).",
             "# `match`: any one of these words must appear in CDAsia's title. `note`: the prof's note.",
             "# `year`: used to pick between several hits. Lines starting with # are ignored.", ""]
    for kind, value in items:
        if kind == "heading":
            lines.append(f"# {value}")
            continue
        case, checks = value
        lines += [f"# CHECK: {c}" for c in checks]
        for i, (k, v) in enumerate(case.items()):
            lead = "- " if i == 0 else "  "
            if k == "match":
                lines.append(f"{lead}{k}: [{', '.join(q(w) for w in v)}]")
            elif k == "year":
                lines.append(f"{lead}{k}: {v}")
            else:
                lines.append(f"{lead}{k}: {q(v)}")
        lines.append("")
    return "\n".join(lines)


def validate(text):
    """Parse yaml text into the case list the downloader expects; raise ValueError saying what's wrong."""
    import yaml
    try:
        cases = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise ValueError(f"not valid yaml: {e}".splitlines()[0]) from None
    if not isinstance(cases, list) or not cases:
        raise ValueError("no cases found")
    for i, c in enumerate(cases, 1):
        if not isinstance(c, dict) or not c.get("name"):
            raise ValueError(f"case {i} has no name")
        if not (c.get("citation") or c.get("gr")):
            raise ValueError(f"{c['name']}: needs a citation or gr")
        if isinstance(c.get("match"), str):
            c["match"] = [c["match"]]
    return cases


if __name__ == "__main__":
    path = Path(sys.argv[1])
    print(to_yaml(path.read_text(), path.name))
