"""Arm E on NIST: zonal OCR, the rules a fixed form allows, learned from the training pages.

SD2's twenty form faces never change layout, so the classic pipeline for them is not label
anchors but zones: each field is a rectangle on the page, and its value is whatever OCR reads
inside it. SD2 publishes no field positions, so the zones are learned, once, from the training
pages' OCR and answer files, and committed (`legible/arms/nist_zones.json`), the way arm E's
rules for the VRDU corpora are committed code:

- **The face.** The words a face prints on at least 90% of its training pages are its template
  words. A page is read as the face whose template words it shows the largest share of.
- **Registration.** A scan sits a little differently on every page. Words the face prints
  exactly once on at least 90% of its training pages are its anchors, each at its median
  position; a page's registration is a scale and a shift on each axis, fitted to where its
  anchors sit against theirs. Samples are learned in the registered frame and zones are
  mapped onto each page when read.
- **A field's zone.** On each training page where the field is filled, the value's letters and
  digits are looked for as a run of consecutive OCR tokens on one line; a page where the run
  is found exactly once gives one sample, its box (a short value such as `0` matches in many
  places and teaches nothing). Samples far from the median centre are dropped as misreads, and
  the zone runs across from the 25th percentile of the rest's left edges to the 95th of their
right edges, and down from the 5th to the 95th percentile of their centres, with half the
median height and a margin above and below (the synthesis jitters each value). A field
  with fewer than three samples gets no zone and is never answered.
- **Reading.** The words whose centres fall in a field's zone, line by line, left to right,
  leaving out the form's own print (a word all of whose letters and digits are words the face
  prints on at least half its training pages: line numbers, labels) and words Tesseract is
  less than 20% sure of (the dotted leaders). Where zones overlap, a word goes to the one whose
  left edge and centre line are nearest it.

Nothing is learned from dev or test. What the zones cannot do is the point of the comparison:
they are exact to a template and say nothing about any other.
"""

from __future__ import annotations

import json
import re
import statistics
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from legible.arms.ocr import OcrPage, Word
from legible.schema import Record
from legible.schema.corpora import SCHEMAS

_TOKEN = re.compile(r"[A-Za-z0-9]+")
TEMPLATE_SHARE = 0.9
PRINTED_SHARE = 0.5
MIN_SAMPLES = 3
#: How far a sample's centre may sit from the median centre and still count, as a share of
#: the page: a row is about 1% of an SD2 page high.
INLIER_X, INLIER_Y = 0.15, 0.01
#: Added on every side of a zone, as a share of the page's width (left and right) or height.
MARGIN_X, MARGIN_Y = 0.006, 0.003
#: Tesseract's confidence below which a word is left out of a read: the dotted leaders the
#: forms print between a label and its box come back as low-confidence strings of letters.
MIN_CONF = 20.0
ZONES = Path(__file__).with_name("nist_zones.json")


def _tokens(text: str) -> list[str]:
    return [t.casefold() for t in _TOKEN.findall(text)]


Box = tuple[float, float, float, float]


class Zone(BaseModel):
    model_config = ConfigDict(frozen=True)

    box: Box
    samples: int


class FaceRules(BaseModel):
    model_config = ConfigDict(frozen=True)

    face: str
    template_words: tuple[str, ...]
    #: Words the face prints on at least half its training pages, left out of every read.
    printed: tuple[str, ...]
    #: Words printed once a page, at their median centre: what a page is registered by.
    anchors: dict[str, tuple[float, float]]
    zones: dict[str, Zone]


def _lines(page: OcrPage) -> list[list[Word]]:
    grouped: dict[tuple[int, int, int], list[Word]] = {}
    for w in page.words:
        grouped.setdefault((w.block, w.par, w.line), []).append(w)
    return [sorted(ws, key=lambda w: w.left) for ws in grouped.values()]


def locate_all(value: str, page: OcrPage) -> list[Box]:
    """The normalised boxes of every run of OCR tokens on one line that spells the value's
    letters and digits."""
    want = _tokens(value)
    found: list[Box] = []
    if not want:
        return found
    for line in _lines(page):
        toks: list[tuple[str, Word]] = [(t, w) for w in line for t in _tokens(w.text)]
        for i in range(len(toks) - len(want) + 1):
            if [t for t, _ in toks[i : i + len(want)]] == want:
                ws = [w for _, w in toks[i : i + len(want)]]
                found.append(
                    (
                        min(w.left for w in ws) / page.width,
                        min(w.top for w in ws) / page.height,
                        max(w.left + w.width for w in ws) / page.width,
                        max(w.top + w.height for w in ws) / page.height,
                    )
                )
    return found


def locate(value: str, page: OcrPage) -> Box | None:
    """The value's box when it is found exactly once on the page, else None."""
    found = locate_all(value, page)
    return found[0] if len(found) == 1 else None


def _inliers(boxes: Sequence[Box]) -> list[Box]:
    cx = statistics.median((b[0] + b[2]) / 2 for b in boxes)
    cy = statistics.median((b[1] + b[3]) / 2 for b in boxes)
    return [
        b
        for b in boxes
        if abs((b[0] + b[2]) / 2 - cx) <= INLIER_X and abs((b[1] + b[3]) / 2 - cy) <= INLIER_Y
    ]


def _unique_centres(page: OcrPage) -> dict[str, tuple[float, float]]:
    """Each word printed exactly once on the page, at its normalised centre."""
    counts: Counter[str] = Counter()
    where: dict[str, tuple[float, float]] = {}
    for w in page.words:
        t = "".join(_tokens(w.text))
        if len(t) > 3:
            counts[t] += 1
            where[t] = ((w.left + w.width / 2) / page.width, (w.top + w.height / 2) / page.height)
    return {t: c for t, c in where.items() if counts[t] == 1}


#: (scale, shift) across and (scale, shift) down: where a point of the face's frame is on a
#: page, `page = scale * frame + shift`.
Transform = tuple[float, float, float, float]
IDENTITY: Transform = (1.0, 0.0, 1.0, 0.0)


def _fit(frame: Sequence[float], seen: Sequence[float]) -> tuple[float, float]:
    """Least squares `seen = a * frame + b`, refitted once without the points it misses by
    more than 1% of the page (a misread anchor). Falls back to a shift alone."""
    pairs = list(zip(frame, seen, strict=True))
    for _ in range(2):
        n = len(pairs)
        if n < 3:
            return 1.0, statistics.median(s - f for f, s in pairs) if pairs else 0.0
        mf = sum(f for f, _ in pairs) / n
        ms = sum(s for _, s in pairs) / n
        var = sum((f - mf) ** 2 for f, _ in pairs)
        a = sum((f - mf) * (s - ms) for f, s in pairs) / var if var else 1.0
        b = ms - a * mf
        kept = [(f, s) for f, s in pairs if abs(a * f + b - s) <= 0.01]
        if len(kept) == n:
            break
        pairs = kept
    return a, b


def register(page: OcrPage, anchors: Mapping[str, tuple[float, float]]) -> Transform:
    """How this page sits against the face's frame, from the anchors it shows."""
    found = _unique_centres(page)
    common = [t for t in anchors if t in found]
    if not common:
        return IDENTITY
    ax, bx = _fit([anchors[t][0] for t in common], [found[t][0] for t in common])
    ay, by = _fit([anchors[t][1] for t in common], [found[t][1] for t in common])
    return ax, bx, ay, by


def to_page(box: Box, t: Transform) -> Box:
    return (t[0] * box[0] + t[1], t[2] * box[1] + t[3], t[0] * box[2] + t[1], t[2] * box[3] + t[3])


def to_frame(box: Box, t: Transform) -> Box:
    return (
        (box[0] - t[1]) / t[0],
        (box[1] - t[3]) / t[2],
        (box[2] - t[1]) / t[0],
        (box[3] - t[3]) / t[2],
    )


def _pct(values: Sequence[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))]


def learn_face(face: str, pages: Iterable[tuple[OcrPage, Record]]) -> FaceRules:
    """One face's template words, anchors and zones from its training pages."""
    pages = list(pages)
    n = len(pages)
    seen: Counter[str] = Counter()
    centres: dict[str, list[tuple[float, float]]] = {}
    for page, _ in pages:
        seen.update(set(_tokens(" ".join(w.text for w in page.words))))
        for t, c in _unique_centres(page).items():
            centres.setdefault(t, []).append(c)
    anchors = {
        t: (statistics.median(x for x, _ in cs), statistics.median(y for _, y in cs))
        for t, cs in sorted(centres.items())
        if len(cs) >= TEMPLATE_SHARE * n
    }
    samples: dict[str, list[Box]] = {}
    for page, truth in pages:
        transform = register(page, anchors)
        for name, value in truth.items():
            if isinstance(value, str) and value.strip():
                box = locate(value, page)
                if box is not None:
                    samples.setdefault(name, []).append(to_frame(box, transform))
    template = tuple(sorted(t for t, c in seen.items() if c >= TEMPLATE_SHARE * n and len(t) > 2))
    printed = tuple(sorted(t for t, c in seen.items() if c >= PRINTED_SHARE * n))
    zones = {}
    for name, found in samples.items():
        boxes = _inliers(found)
        if len(boxes) < MIN_SAMPLES:
            continue
        middles = [(b[1] + b[3]) / 2 for b in boxes]
        half = statistics.median(b[3] - b[1] for b in boxes) / 2 + MARGIN_Y
        zones[name] = Zone(
            box=(
                max(0.0, _pct([b[0] for b in boxes], 0.25) - MARGIN_X),
                max(0.0, _pct(middles, 0.05) - half),
                min(1.0, _pct([b[2] for b in boxes], 0.95) + MARGIN_X),
                min(1.0, _pct(middles, 0.95) + half),
            ),
            samples=len(boxes),
        )
    return FaceRules(
        face=face, template_words=template, printed=printed, anchors=anchors, zones=zones
    )


def save(rules: Mapping[str, FaceRules], path: Path = ZONES) -> None:
    body = {f: r.model_dump(mode="json") for f, r in sorted(rules.items())}
    path.write_text(json.dumps(body, indent=1) + "\n", encoding="utf-8", newline="\n")


def load_rules(path: Path = ZONES) -> dict[str, FaceRules]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {f: FaceRules.model_validate(r) for f, r in raw.items()}


def identify(page: OcrPage, rules: Mapping[str, FaceRules]) -> str | None:
    """The face whose template words the page shows the largest share of."""
    have = set(_tokens(" ".join(w.text for w in page.words)))
    scored = [
        (sum(t in have for t in r.template_words) / len(r.template_words), f)
        for f, r in rules.items()
        if r.template_words
    ]
    return max(scored)[1] if scored else None


def _centre(w: Word, page: OcrPage) -> tuple[float, float]:
    return (w.left + w.width / 2) / page.width, (w.top + w.height / 2) / page.height


def _in(c: tuple[float, float], box: Box) -> bool:
    return box[0] <= c[0] <= box[2] and box[1] <= c[1] <= box[3]


def _join(inside: list[Word]) -> str | None:
    if not inside:
        return None
    # Line by line: words whose tops are within half a word's height are one line.
    inside.sort(key=lambda w: (w.top, w.left))
    height = statistics.median(w.height for w in inside)
    rows: list[list[Word]] = []
    for w in inside:
        if rows and abs(w.top - rows[-1][0].top) <= height / 2:
            rows[-1].append(w)
        else:
            rows.append([w])
    return " ".join(" ".join(x.text for x in sorted(r, key=lambda w: w.left)) for r in rows)


def _printed(w: Word, form: set[str]) -> bool:
    """Whether a word is the form's own print: all its letters and digits are words the face
    prints on at least half its training pages. A value that shares them (the "and" of a joint
    filer's name) is lost with them; keeping such words let the labels in instead, and read
    worse on dev (14.4% of fields right against 17.5%)."""
    toks = _tokens(w.text)
    return bool(toks) and all(t in form for t in toks)


def read_zone(page: OcrPage, box: Box, printed: Iterable[str] = ()) -> str | None:
    """The words whose centres fall in one zone, the form's own print left out."""
    form = set(printed)
    return _join([w for w in page.words if _in(_centre(w, page), box) and not _printed(w, form)])


def read_zones(page: OcrPage, boxes: Mapping[str, Box], printed: Iterable[str] = ()) -> Record:
    """Every zone at once, each word given to one field only: where zones overlap (the
    columns of a dependants table do), to the zone whose left edge is nearest to its left, the
    way a value is written from the start of its box."""
    form = set(printed)
    taken: dict[str, list[Word]] = {name: [] for name in boxes}
    for w in page.words:
        if w.conf < MIN_CONF or _printed(w, form):
            continue
        c = _centre(w, page)
        hits = [name for name, box in boxes.items() if _in(c, box)]
        if hits:
            left, cy = w.left / page.width, c[1]
            nearest = min(
                hits,
                key=lambda n: abs(boxes[n][0] - left) + abs((boxes[n][1] + boxes[n][3]) / 2 - cy),
            )
            taken[nearest].append(w)
    return {name: _join(ws) for name, ws in taken.items()}


def read(page: OcrPage, rules: Mapping[str, FaceRules]) -> tuple[str | None, Record]:
    """(the face the page was read as, its record in that face's schema)."""
    face = identify(page, rules)
    if face is None:
        return None, {}
    zones, printed = rules[face].zones, rules[face].printed
    transform = register(page, rules[face].anchors)
    schema = SCHEMAS[f"nist_{face.lower()}"]
    found = read_zones(page, {n: to_page(z.box, transform) for n, z in zones.items()}, printed)
    record: Record = {f.name: found.get(f.name) for f in schema.scalars}
    return face, record
