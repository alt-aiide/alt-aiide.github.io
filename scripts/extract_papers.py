#!/usr/bin/env python3
"""Extract title, authors and abstract from every PDF in papers/ and write
_data/papers.yml for the Jekyll site.

Requires poppler-utils (pdftohtml, pdftotext) and PyYAML.

The papers use the AAAI two-column template, so the first page is parsed by
font size: the largest font is the title, the next one the author names, and
the abstract is the body text under the bold "Abstract" heading, up to the
first section heading.

Usage:  python3 scripts/extract_papers.py [--papers DIR] [--out FILE]
"""

import argparse
import hashlib
import html
import re
import subprocess
import unicodedata
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

LIGATURES = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl"}
SUP = dict(zip("0123456789+-−=()ni", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁻⁼⁽⁾ⁿⁱ"))
SUB = dict(zip("0123456789+-−=()", "₀₁₂₃₄₅₆₇₈₉₊₋₋₌₍₎"))

# keyword (regex, case-insensitive) -> badge label
TAGS = [
    (r"monte carlo tree search|\bmcts\b|ismcts", "MCTS"),
    (r"\bdqn\b|deep q|q-network", "Deep Q-Learning"),
    (r"tabular q-learning|\bq-learning\b", "Q-Learning"),
    (r"alpha.beta", "Alpha–Beta"),
    (r"expectimax", "Expectimax"),
    (r"plan recognition", "Plan Recognition"),
    (r"opponent model", "Opponent Modelling"),
    (r"imperfect information|hidden hand|information set", "Imperfect Information"),
    (r"equivarian|symmetr", "Symmetry"),
    (r"ablat", "Ablation"),
    (r"belief", "Beliefs"),
    (r"battleship", "Battleship"),
    (r"backgammon", "Backgammon"),
    (r"draughts|checkers", "Checkers"),
    (r"azul", "Azul"),
    (r"prisoner", "Prisoner's Dilemma"),
    (r"exploding kittens", "Exploding Kittens"),
    (r"card game", "Card Games"),
    (r"board game", "Board Games"),
]

HYPE_POOL = [
    "Reviewers reported spontaneous standing ovations while reading the abstract alone.",
    "Experts agree: the field will now be divided into 'before this paper' and 'after this paper'.",
    "Contains at least one result so novel that our servers briefly refused to index it.",
    "Peer review was waived on the grounds that no peer could be found.",
    "Rumoured to have been cited by papers that have not yet been written.",
    "Our committee rated it 11/10, which our review form does not technically allow.",
]


def run(cmd):
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout


# LaTeX accents often come out as a spacing accent before the base letter
# ("R´ıos"); turn them into proper composed characters ("Ríos").
ACCENTS = {"´": "\u0301", "`": "\u0300", "¨": "\u0308", "ˆ": "\u0302", "˜": "\u0303",
           "ˇ": "\u030c", "¸": "\u0327", "˚": "\u030a", "˙": "\u0307", "˝": "\u030b"}
ACCENT_RE = re.compile("([" + "".join(ACCENTS) + "])([A-Za-zıȷ])")


def fix_accents(s):
    s = ACCENT_RE.sub(lambda m: m.group(2).replace("ı", "i").replace("ȷ", "j") + ACCENTS[m.group(1)], s)
    s = re.sub("[ıȷ](?=[\u0300-\u036f])", lambda m: "i" if m.group(0) == "ı" else "j", s)
    return unicodedata.normalize("NFC", s)


def clean(s):
    for k, v in LIGATURES.items():
        s = s.replace(k, v)
    return fix_accents(s)


class Frag:
    def __init__(self, el, fonts):
        self.top = int(el.get("top"))
        self.left = int(el.get("left"))
        self.width = int(el.get("width"))
        self.height = int(el.get("height"))
        self.font = el.get("font")
        self.size, self.family = fonts[self.font]
        self.text = clean("".join(el.itertext()))

    @property
    def right(self):
        return self.left + self.width

    @property
    def bold(self):
        return bool(re.search(r"Medi|Bold|-Bd|Semibold", self.family))


def first_page(pdf):
    xml = run(["pdftohtml", "-xml", "-i", "-q", "-f", "1", "-l", "1", "-stdout", str(pdf)])
    root = ET.fromstring(xml)
    page = root.find("page")
    fonts = {f.get("id"): (int(f.get("size")), f.get("family")) for f in page.iter("fontspec")}
    frags = [Frag(t, fonts) for t in page.iter("text")]
    frags = [f for f in frags if f.text.strip()]
    return frags, int(page.get("width"))


def group_lines(frags):
    """Group fragments into visual lines, top-down, each sorted left-to-right.

    Lines are seeded from fragments in the dominant font; everything else
    (math, super/subscripts, symbols) is attached to the line it overlaps most
    vertically without colliding horizontally with text already on it.
    """
    if not frags:
        return []
    weight = {}
    for f in frags:
        weight[f.font] = weight.get(f.font, 0) + f.width
    main = max(weight, key=weight.get)
    lines = []  # each: {"top", "bottom", "frags"}
    for f in sorted((f for f in frags if f.font == main), key=lambda f: (f.top, f.left)):
        c = f.top + f.height / 2
        for ln in lines:
            if abs(c - (ln["top"] + ln["bottom"]) / 2) <= f.height / 2:
                ln["frags"].append(f)
                ln["top"], ln["bottom"] = min(ln["top"], f.top), max(ln["bottom"], f.top + f.height)
                break
        else:
            lines.append({"top": f.top, "bottom": f.top + f.height, "frags": [f]})
    for f in sorted((f for f in frags if f.font != main), key=lambda f: -f.size):
        best, best_ov = None, 0
        for ln in lines:
            ov = min(ln["bottom"], f.top + f.height) - max(ln["top"], f.top)
            if ov <= 0 or any(g.left < f.right - 1 and f.left < g.right - 1 for g in ln["frags"]):
                continue
            if ov > best_ov:
                best, best_ov = ln, ov
        if best is None:
            lines.append({"top": f.top, "bottom": f.top + f.height, "frags": [f]})
        else:
            best["frags"].append(f)
    lines.sort(key=lambda ln: ln["top"])
    return [sorted(ln["frags"], key=lambda f: f.left) for ln in lines]


def script_text(t, raised):
    t = t.strip()
    table = SUP if raised else SUB
    if all(c in table for c in t):
        return "".join(table[c] for c in t)
    mark = "^" if raised else "_"
    return mark + (t if len(t) == 1 else f"({t})")


def line_text(frags, body_size):
    """Join a line's fragments, turning small raised/lowered text into sup/subscripts."""
    big = [f for f in frags if f.size >= body_size * 0.8] or frags
    mid = sum(f.top + f.height / 2 for f in big) / len(big)
    parts = []
    prev = None
    for f in frags:
        t = f.text
        if f.size < body_size * 0.8 and t.strip():
            t = script_text(t, f.top + f.height / 2 < mid)
            sep = " " if prev is not None and f.left - prev.right > 3 else ""
        else:
            sep = " " if prev is not None and f.left - prev.right > 1 else ""
        parts.append(sep + t)
        prev = f
    return fix_accents(re.sub(r"\s+", " ", "".join(parts)).strip())


def join_lines(lines, vocab):
    """Join text lines, undoing end-of-line hyphenation.

    A line-final hyphen is dropped (pa- per -> paper) unless both halves are
    words the paper uses on their own and the joined form never appears, in
    which case it is a real compound (dependency- free -> dependency-free).
    """
    words = vocab["words"]
    text = ""
    for ln in lines:
        if not text:
            text = ln
            continue
        m = re.search(r"([A-Za-z’']*)-$", text)
        if m and re.match(r"[a-z]", ln):
            pre = m.group(1)
            suf = re.match(r"[a-z’']+", ln).group(0)
            joined = (pre + suf).lower()
            compound = (
                (pre + "-" + suf).lower() in vocab["hyph"]
                or (len(pre) >= 4 and pre.lower() in words and suf in words)
            ) and joined not in words
            text = text + ln if compound else text[:-1] + ln
        elif m or text.endswith("–"):
            text = text + ln  # "Q-" + "Learning", "Knuth–" + "Moore"
        else:
            text = text + " " + ln
    return text


def build_vocab(pdf):
    """Words/compounds the paper uses, from un-dehyphenated fragment text."""
    xml = run(["pdftohtml", "-xml", "-i", "-q", "-stdout", str(pdf)])
    root = ET.fromstring(xml)
    words, hyph = set(), set()
    for t in root.iter("text"):
        s = clean("".join(t.itertext())).strip()
        if s.endswith("-"):
            s = s.rsplit(" ", 1)[0] if " " in s else ""
        for tok in re.findall(r"[A-Za-z’']+(?:-[A-Za-z’']+)*", s):
            tok = tok.lower()
            if "-" in tok:
                hyph.add(tok)
                words.update(tok.split("-"))
            else:
                words.add(tok)
    return {"words": words, "hyph": hyph}


AUTHOR_SEP = re.compile(r"\s*,\s*|\s+and\s+|^and\s+|\s*&\s*")
MARKER_RE = re.compile(r"^[\s,]*(?:[0-9]+|[*†‡§¶])(?:[\s,]*(?:[0-9]+|[*†‡§¶]))*[\s,]*$")


def is_marker(f, ref_size):
    return f.size < ref_size * 0.85 and bool(MARKER_RE.match(f.text))


def parse_authors(lines, author_size):
    """Walk the author line(s) left to right. Bold text accumulates names (split
    on commas/and/&); small superscript fragments are affiliation markers for the
    name just finished. Returns [{"name", "markers", "left", "right"}]."""
    names = []
    cur = {"text": "", "left": None, "right": None}

    def finish():
        name = re.sub(r"\s+", " ", cur["text"]).strip(" ,")
        if name:
            names.append({"name": fix_accents(name), "markers": [], "left": cur["left"], "right": cur["right"]})
        cur.update(text="", left=None, right=None)

    for line in lines:
        prev = None
        for f in line:
            if is_marker(f, author_size):
                finish()
                if names:
                    names[-1]["markers"] += [m for m in re.split(r"[\s,]+", f.text.strip()) if m]
                prev = f
                continue
            text = (" " if prev is not None and f.left - prev.right > 1 else "") + f.text
            pieces = AUTHOR_SEP.split(text)
            for i, piece in enumerate(pieces):
                if i > 0:
                    finish()
                if piece.strip():
                    cur["text"] += piece
                    cur["left"] = f.left if cur["left"] is None else min(cur["left"], f.left)
                    cur["right"] = f.right if cur["right"] is None else max(cur["right"], f.right)
            prev = f
        finish()
    return names


def parse_affiliations(lines, names):
    """Map affiliation lines (below the author names) to authors.

    Handles three layouts: numbered markers (1Dept..., 2Dept...), AAAI side-by-side
    author columns, and a single shared affiliation block. Returns
    (affiliations, per-author list of 1-based affiliation indices)."""
    lines = [l for l in lines if "@" not in "".join(f.text for f in l)]
    lines = [l for l in lines if line_text(l, max(f.size for f in l)).strip()]
    if not lines:
        return [], [[] for _ in names]

    def text_of(l):
        return line_text(l, max(f.size for f in l))

    # 1) numbered / symbol markers
    marked, order, last = {}, [], None
    for l in lines:
        size = max(f.size for f in l)
        if is_marker(l[0], size):
            last = l[0].text.strip()
            marked[last] = text_of(l[1:]) if len(l) > 1 else ""
            order.append(last)
        elif last is not None:
            marked[last] += ", " + text_of(l)
    if marked and any(n["markers"] for n in names):
        affs = [marked[m] for m in order]
        idx = [[order.index(m) + 1 for m in n["markers"] if m in marked] for n in names]
        return affs, [i or [1] for i in idx]

    # 2) side-by-side columns: each line sits under exactly one author
    def under(l):
        lo, hi = min(f.left for f in l), max(f.right for f in l)
        return [i for i, n in enumerate(names) if n["left"] is not None and n["left"] < hi and lo < n["right"]]

    if len(names) > 1 and all(len(under(l)) == 1 for l in lines):
        affs, idx = [], []
        for i in range(len(names)):
            mine = [text_of(l) for l in lines if under(l) == [i]]
            if not mine:
                idx.append([])
                continue
            if mine[0] not in affs:
                affs.append(mine[0])
            idx.append([affs.index(mine[0]) + 1])
        return affs, idx

    # 3) one shared block: first line is the institution, the rest is address
    return [text_of(lines[0])], [[1] for _ in names]


def extract(pdf):
    frags, page_w = first_page(pdf)
    warnings = []
    sizes = sorted({f.size for f in frags}, reverse=True)

    abs_head = next((f for f in frags if f.text.strip() == "Abstract" and f.bold), None)
    head_limit = abs_head.top if abs_head else 400

    # --- title: largest font above the abstract heading
    title_size = max(f.size for f in frags if f.top < head_limit)
    title_frags = [f for f in frags if f.size == title_size and f.top < head_limit]
    title_lines = group_lines(title_frags)
    title = " ".join(line_text(l, title_size) for l in title_lines)
    title_bottom = max(f.top + f.height for f in title_frags)

    # --- authors: next-largest font between title and abstract heading
    rest = [f for f in frags if title_bottom <= f.top < head_limit]
    author_size = max((f.size for f in rest), default=None)
    authors, affiliations = [], []
    if author_size:
        a_frags = [f for f in rest if f.size == author_size and f.bold]
        if not a_frags:
            a_frags = group_lines([f for f in rest if f.size == author_size])[0]
        a_top = min(f.top for f in a_frags)
        a_bottom = max(f.top + f.height for f in a_frags)
        # superscript markers sit on the author lines but in a smaller font
        a_marks = [f for f in rest if f not in a_frags and is_marker(f, author_size)
                   and a_top - 4 <= f.top + f.height / 2 <= a_bottom]
        names = parse_authors(group_lines(a_frags + a_marks), author_size)
        used = set(map(id, a_frags + a_marks))
        aff_lines = group_lines([f for f in rest if id(f) not in used and f.top >= a_bottom - 2])
        affiliations, idx = parse_affiliations(aff_lines, names)
        authors = [{"name": n["name"], "affiliations": i} for n, i in zip(names, idx)]
    if not authors:
        warnings.append("no authors found")

    # --- abstract
    abstract = ""
    if abs_head:
        body = [f for f in frags if f.top > abs_head.top + abs_head.height - 2]
        body_size = max(set(f.size for f in body), key=lambda s: sum(f.width for f in body if f.size == s))
        mid = page_w / 2
        col_l = [f for f in body if f.left < mid and abs_head.left - 200 < f.left]
        lines = []
        done = False
        for ln in group_lines(col_l):
            first = ln[0]
            txt = line_text(ln, body_size)
            if (first.bold and first.size >= abs_head.size) or txt.startswith("Copyright"):
                done = True
                break
            lines.append(txt)
        if not done:
            # abstract continues at the top of the right column
            col_r = [f for f in frags if f.left >= mid]
            for ln in group_lines(col_r):
                first = ln[0]
                txt = line_text(ln, body_size)
                if (first.bold and first.size >= abs_head.size) or txt.startswith("Copyright"):
                    break
                lines.append(txt)
            warnings.append("abstract continued into right column — check it")
        abstract = join_lines(lines, build_vocab(pdf))
    if not abstract:
        warnings.append("font-based abstract extraction failed, using text fallback")
        txt = clean(run(["pdftotext", "-q", "-l", "1", str(pdf), "-"]))
        m = re.search(r"Abstract\s*(.+?)\n\s*(?:1\s*)?Introduction", txt, re.S)
        abstract = re.sub(r"-\n(?=[a-z])", "", m.group(1)).replace("\n", " ") if m else ""
        abstract = re.sub(r"\s+", " ", abstract).strip()
    if not abstract:
        warnings.append("NO ABSTRACT")

    hay = (title + " " + abstract).lower()
    tags = []
    for pat, label in TAGS:
        if re.search(pat, hay) and label not in tags:
            tags.append(label)
    if "Deep Q-Learning" in tags and "Q-Learning" in tags:
        tags.remove("Q-Learning")

    return {
        "file": pdf.name,
        "title": title,
        "authors": authors,
        "affiliations": affiliations,
        "abstract": abstract,
        "tags": tags[:5],
    }, warnings


def default_hype(name):
    h = int(hashlib.md5(name.encode()).hexdigest(), 16)
    return HYPE_POOL[h % len(HYPE_POOL)]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--papers", default=ROOT / "papers", type=Path)
    ap.add_argument("--out", default=ROOT / "_data" / "papers.yml", type=Path)
    ap.add_argument("--hype", default=ROOT / "_data" / "hype_overrides.yml", type=Path,
                    help="YAML mapping of PDF filename -> hand-written hype blurb")
    args = ap.parse_args()

    overrides = {}
    if args.hype.exists():
        overrides = yaml.safe_load(args.hype.read_text(encoding="utf-8")) or {}

    pdfs = sorted(args.papers.glob("*.pdf"), key=lambda p: [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", p.name)])
    if not pdfs:
        sys.exit(f"No PDFs found in {args.papers}")

    papers = []
    for pdf in pdfs:
        try:
            info, warns = extract(pdf)
        except Exception as e:  # keep going; one broken PDF shouldn't kill the site
            print(f"!! {pdf.name}: extraction failed: {e}", file=sys.stderr)
            continue
        info["hype"] = overrides.get(pdf.name) or default_hype(pdf.name)
        papers.append(info)
        print(f"{pdf.name:14} {', '.join(a['name'] for a in info['authors'])[:30]:30} {info['title'][:70]}")
        print(f"{'':14} abstract: {len(info['abstract'].split())} words; tags: {', '.join(info['tags'])}")
        for w in warns:
            print(f"{'':14} WARNING: {w}", file=sys.stderr)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as fh:
        fh.write("# Generated by scripts/extract_papers.py — do not edit by hand.\n")
        yaml.safe_dump(papers, fh, allow_unicode=True, sort_keys=False, width=1000)
    print(f"\nWrote {len(papers)} papers to {args.out.relative_to(ROOT) if args.out.is_relative_to(ROOT) else args.out}")


if __name__ == "__main__":
    main()
