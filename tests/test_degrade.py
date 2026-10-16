"""Degradation is reproducible byte for byte and gets worse with the level."""

from __future__ import annotations

import hashlib
import itertools

import numpy as np
import pytest
from PIL import Image, ImageDraw

from legible.degrade import LEVELS, degrade, seed_for, to_png


def page(mode: str = "1") -> Image.Image:
    """A small synthetic form: ruled boxes and blocks of 'text'."""
    img = Image.new("L", (600, 800), 255)
    draw = ImageDraw.Draw(img)
    for y in range(60, 760, 70):
        draw.rectangle((40, y, 560, y + 50), outline=0, width=2)
        for x in range(60, 520, 24):
            draw.rectangle((x, y + 15, x + 14, y + 35), fill=0)
    return img.convert(mode)


@pytest.mark.parametrize("level", range(len(LEVELS)))
@pytest.mark.parametrize("mode", ["1", "RGB"])
def test_same_page_same_level_same_bytes(level: int, mode: str) -> None:
    a = to_png(degrade(page(mode), "nist/f0001_01", level))
    b = to_png(degrade(page(mode), "nist/f0001_01", level))
    assert hashlib.sha256(a).hexdigest() == hashlib.sha256(b).hexdigest()


def test_different_pages_draw_different_noise() -> None:
    a = to_png(degrade(page(), "nist/f0001_01", 3))
    b = to_png(degrade(page(), "nist/f0002_01", 3))
    assert a != b


def test_seed_is_stable_across_processes() -> None:
    # A fixed value, so a change to the seeding (which would change every degraded page and
    # invalidate the calibration) fails here rather than silently.
    assert seed_for("nist/f0001_01", 3) == seed_for("nist/f0001_01", 3)
    assert seed_for("nist/f0001_01", 3) != seed_for("nist/f0001_01", 4)
    assert seed_for("x", 1, 16) == int.from_bytes(hashlib.sha256(b"16:1:x").digest()[:8], "big")


def test_level_zero_is_the_page() -> None:
    src = page("L")
    assert np.array_equal(np.array(degrade(src, "p", 0)), np.array(src))


def test_geometry_is_kept_and_every_level_damages() -> None:
    # Pixel error is not monotone in the level (blur hides noise), which is why the levels
    # are calibrated by OCR word accuracy rather than by any pixel measure.
    src = np.array(page("L"), dtype=float)
    errors = []
    for level in range(len(LEVELS)):
        out = degrade(page(), "p", level)
        assert out.size == (600, 800)
        errors.append(float(np.abs(np.array(out, dtype=float) - src).mean()))
    assert errors[0] == 0
    assert all(e > 0 for e in errors[1:])


def test_levels_are_cumulative() -> None:
    for lower, higher in itertools.pairwise(LEVELS):
        assert higher.dpi <= lower.dpi
        assert higher.blur >= lower.blur
        assert higher.skew >= lower.skew
        assert higher.noise >= lower.noise
        if lower.jpeg_quality is not None:
            assert higher.jpeg_quality is not None and higher.jpeg_quality <= lower.jpeg_quality
