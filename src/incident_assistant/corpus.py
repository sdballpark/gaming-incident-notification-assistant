"""
Regulation corpus and retrieval.

The regulation text is retrieved, never recalled. The rule changed in January 2026,
and a model trained before that may still believe the deadline is 72 hours.

The corpus is one regulation of a few pages, split into subsections. Keyword
retrieval with BM25 is enough at that size: every subsection fits in a single
result, and an exact citation like 4(a) matters more than semantic similarity.
Vector search would add a dependency and a model without improving recall here.

Each section has an id such as "4(a)", which is how drafts cite it: [Reg 5.260(4)(a)].
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CORPUS = Path(__file__).parent / "data" / "corpus" / "reg-5.260-2026-01-29.json"

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = frozenset("a an and are as at be by for from has have in is it its of on or "
                  "shall such that the this to was were which with any all".split())


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOP]


@dataclass(frozen=True)
class Section:
    id: str
    title: str
    text: str


class Corpus:
    def __init__(self, sections: list[Section], source: dict[str, str]):
        if not sections:
            raise ValueError("corpus has no sections")
        ids = [s.id for s in sections]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate section ids")
        self.sections = {s.id: s for s in sections}
        self.source = source
        self._docs = {s.id: _tokens(f"{s.title} {s.text}") for s in sections}
        self._avgdl = sum(len(d) for d in self._docs.values()) / len(self._docs)
        df: dict[str, int] = {}
        for toks in self._docs.values():
            for t in set(toks):
                df[t] = df.get(t, 0) + 1
        n = len(self._docs)
        self._idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    @classmethod
    def load(cls, path: str | Path = DEFAULT_CORPUS) -> "Corpus":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls([Section(**s) for s in data["sections"]], data["source"])

    def resolve(self, section_id: str) -> Section | None:
        return self.sections.get(section_id)

    def search(self, query: str, k: int = 3) -> list[dict[str, str | float]]:
        q = _tokens(query)
        k1, b = 1.5, 0.75
        scored = []
        for sid, doc in self._docs.items():
            score = 0.0
            dl = len(doc)
            for t in q:
                f = doc.count(t)
                if f:
                    score += self._idf.get(t, 0.0) * f * (k1 + 1) / (
                        f + k1 * (1 - b + b * dl / self._avgdl))
            if score > 0:
                scored.append((score, sid))
        scored.sort(key=lambda x: (-x[0], x[1]))
        return [{"id": sid, "cite": cite(sid), "title": self.sections[sid].title,
                 "text": self.sections[sid].text, "score": round(s, 3)}
                for s, sid in scored[:k]]


_SECTION_ID = re.compile(r"^(\d+)((?:\([a-z0-9]+\))*)$")


def cite(section_id: str) -> str:
    """'4(a)' -> '[Reg 5.260(4)(a)]', '2' -> '[Reg 5.260(2)]'."""
    m = _SECTION_ID.match(section_id)
    if not m:
        raise ValueError(f"not a section id: {section_id}")
    return f"[Reg 5.260({m.group(1)}){m.group(2)}]"


_CITE = re.compile(r"\[Reg 5\.260\((\d+)\)((?:\([a-z0-9]+\))*)\]")


def parse_cites(text: str) -> list[str]:
    """Section ids cited in text, in order: '[Reg 5.260(4)(a)]' -> '4(a)'."""
    return [m.group(1) + m.group(2) for m in _CITE.finditer(text)]
