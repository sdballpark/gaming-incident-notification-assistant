"""
Build the regulation corpus from the official adopted text.

Source: Nevada Gaming Commission, amendments to Regulation 5.260, adopted and effective
January 29, 2026. The PDF is downloaded from gaming.nv.gov and its text extracted with
pypdf; this script turns that text into the sections the assistant retrieves.

The adopted document is a markup: deleted wording appears in [brackets] inline, for
example "no later than [72] 24 hours". Text extraction keeps the brackets but loses the
strikethrough, so the brackets are the only marker. Every bracketed span is removed.
Brackets are treated as non-nesting because the extraction contains one deleted
paragraph whose own text included an older bracket ("[(b) ... [cyber attacks.]"),
and only that reading removes the whole paragraph.

Checks run after cleaning, and the build fails if any of them do not hold:
  - no brackets remain
  - the number 72 appears nowhere in the cleaned text
  - section 4(a) contains "24 hours" and "activating the response procedures"
  - every expected section id is present

Usage:
    python scripts/build_corpus.py <extracted.txt> <pdf-sha256>
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

OUT = Path("src/incident_assistant/data/corpus/reg-5.260-2026-01-29.json")
SOURCE_URL = ("https://www.gaming.nv.gov/siteassets/content/divisions/administration/"
              "history/regulation-5.260-adp-01.29.2026-eff-01.29.2026.pdf")

# Word breaks introduced by PDF text extraction, corrected explicitly so each fix is
# visible and reviewable rather than hidden in a general rule.
EXTRACTION_FIXES = {
    "third -party": "third-party",
    "Framework fo r": "Framework for",
    "ISO/IEC 2 7001": "ISO/IEC 27001",
    "NIST SP 800 -53": "NIST SP 800-53",
    "attes t": "attest",
    "cyber security incident": "cybersecurity incident",
}

TITLES = {
    "1": "Policy",
    "2": "Definitions",
    "2(a)": "Definition: Board", "2(b)": "Definition: Chair",
    "2(c)": "Definition: Cybersecurity", "2(d)": "Definition: Cybersecurity incident",
    "2(e)": "Definition: Cybersecurity incident response plan",
    "2(f)": "Definition: Covered entity", "2(g)": "Definition: Information system",
    "2(h)": "Definition: Risk assessment",
    "3": "Risk assessment and cybersecurity best practices",
    "4": "Reporting obligations after a cybersecurity incident",
    "4(a)": "Initial notification to the Chair within 24 hours",
    "4(b)": "Initial Cybersecurity Incident Response report",
    "4(c)": "Written status updates every 30 days",
    "4(d)": "Information on request",
    "4(e)": "Investigation report",
    "4(f)": "External investigations",
    "4(waiver)": "Waiver or modification of reporting requirements",
    "5": "Group I licensees",
    "5(a)": "Qualified individual", "5(b)": "Annual internal audit",
    "5(c)": "Annual independent review and attestation",
    "6": "Documentation and record retention",
    "7": "Enforcement",
}


def strip_deletions(text: str) -> str:
    out, deleting = [], False
    for ch in text:
        if ch == "[":
            deleting = True
        elif ch == "]":
            deleting = False
        elif not deleting:
            out.append(ch)
    return "".join(out)


_PRIVATE_USE = re.compile("[\ue000-\uf8ff]")


def body_lines(raw: str) -> list[str]:
    # The PDF marks the waiver paragraph with a symbol-font glyph (U+F0CA) that
    # extracts as a private-use character. Private-use characters carry no text.
    lines = _PRIVATE_USE.sub("", raw).splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.strip().startswith("5.260 Cybersecurity"))
    return [ln for ln in lines[start + 1:] if not re.match(r"^Page \d+\s+Dated:", ln)]


def normalize(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    for bad, good in EXTRACTION_FIXES.items():
        text = text.replace(bad, good)
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    return re.sub(r"\s{2,}", " ", text)


def split_sections(lines: list[str]) -> dict[str, str]:
    """Walk the cleaned lines and assign each to a section id."""
    sections: dict[str, list[str]] = {}
    top, current = None, None
    for ln in lines:
        stripped = ln.strip()
        m_top = re.match(r"^(\d)\.\s", stripped)
        m_par = re.match(r"^\(([a-h])\)\s", stripped)
        if m_top:
            top = m_top.group(1)
            current = top
        elif m_par and top in {"2", "4", "5"}:
            current = f"{top}({m_par.group(1)})"
        elif top == "4" and stripped.startswith("The Chair, in the Chair"):
            current = "4(waiver)"
        if current is None:
            continue
        sections.setdefault(current, []).append(ln)
    return {sid: normalize(" ".join(parts)) for sid, parts in sections.items()}


def build(txt_path: str, pdf_sha256: str) -> dict:
    raw = Path(txt_path).read_text(encoding="utf-8")
    # Deletions can span lines, so they are stripped from the joined text.
    joined = strip_deletions("\n".join(body_lines(raw)))
    cleaned_lines = joined.splitlines()
    sections = split_sections(cleaned_lines)

    full = " ".join(sections.values())
    problems = []
    if "[" in full or "]" in full:
        problems.append("brackets remain after cleaning")
    if re.search(r"\b72\b", full):
        problems.append("the number 72 appears in the cleaned text")
    a = sections.get("4(a)", "")
    if "24 hours" not in a or "activating the response procedures" not in a:
        problems.append("4(a) does not read as the amended 24-hour rule")
    missing = sorted(set(TITLES) - set(sections))
    extra = sorted(set(sections) - set(TITLES))
    if missing:
        problems.append(f"missing sections: {missing}")
    if extra:
        problems.append(f"unexpected sections: {extra}")
    if problems:
        raise SystemExit("corpus build failed: " + "; ".join(problems))

    return {
        "source": {
            "title": "Nevada Gaming Commission Regulation 5.260, as amended",
            "adopted": "2026-01-29",
            "effective": "2026-01-29",
            "url": SOURCE_URL,
            "pdf_sha256": pdf_sha256,
            "extracted_text_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
            "extraction": "pypdf; deleted [bracketed] text removed; private-use "
                          "glyphs removed; word-break fixes listed in scripts/build_corpus.py",
        },
        "sections": [{"id": sid, "title": TITLES[sid], "text": sections[sid]}
                     for sid in TITLES],
    }


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    corpus = build(sys.argv[1], sys.argv[2])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(corpus, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT}: {len(corpus['sections'])} sections")
