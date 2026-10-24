"""Scan degradation, levels 0 to 4, reproducible byte for byte.

Level 0 is the page rasterised at 300 dpi. Each level above it applies, in order and more
strongly than the level below, the five things that go wrong between a form and its scan:
resolution lost (down to the level's dpi and back up, so that annotation coordinates stay
valid while the detail is gone), blur, skew, salt-and-pepper noise and JPEG recompression.
Every random draw comes from a generator seeded by the page id, the level and a base seed,
so the same page at the same level is the same bytes on every machine with the same Pillow,
and the test suite holds that true.

The parameters below are what "level 3" means mechanically. What it means for reading is
measured once, by Tesseract word accuracy on the NIST clean pages, and written to
docs/degradation.md; a result is reported against that calibration, not against this table.
07's scanned track imports this module and reads that document.
"""

from __future__ import annotations

import hashlib
import io
from typing import Final

import numpy as np
from PIL import Image, ImageFilter
from pydantic import BaseModel, ConfigDict, Field

#: The resolution every corpus is rasterised to before degradation.
SOURCE_DPI: Final = 300
BASE_SEED: Final = 16


class Level(BaseModel):
    """One degradation level's parameters."""

    model_config = ConfigDict(frozen=True)

    level: int = Field(ge=0, le=4)
    #: Resolution the page is resampled to and back from.
    dpi: int
    #: Gaussian blur radius in pixels at 300 dpi.
    blur: float
    #: Largest skew in degrees; the angle is drawn uniformly from [-skew, skew].
    skew: float
    #: Share of pixels set to black or white at random.
    noise: float
    #: JPEG quality of the final recompression, or None for no recompression.
    jpeg_quality: int | None


LEVELS: Final[tuple[Level, ...]] = (
    Level(level=0, dpi=300, blur=0.0, skew=0.0, noise=0.0, jpeg_quality=None),
    Level(level=1, dpi=200, blur=0.5, skew=0.5, noise=0.001, jpeg_quality=85),
    Level(level=2, dpi=150, blur=0.8, skew=1.0, noise=0.005, jpeg_quality=60),
    Level(level=3, dpi=120, blur=1.2, skew=2.0, noise=0.01, jpeg_quality=40),
    Level(level=4, dpi=100, blur=1.6, skew=3.0, noise=0.02, jpeg_quality=25),
)


def seed_for(page_id: str, level: int, base_seed: int = BASE_SEED) -> int:
    """The generator seed for one page at one level. A hash, not Python's hash(), which is
    salted per process."""
    digest = hashlib.sha256(f"{base_seed}:{level}:{page_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def degrade(
    image: Image.Image, page_id: str, level: int, *, base_seed: int = BASE_SEED
) -> Image.Image:
    """The page at a degradation level. Level 0 returns the page unchanged (as greyscale or
    RGB). Binary pages are promoted to greyscale first, because blur and JPEG are not
    defined on one bit."""
    spec = LEVELS[level]
    page = (
        image.convert("L") if image.mode in {"1", "L", "P", "I", "I;16"} else image.convert("RGB")
    )
    if spec.level == 0:
        return page
    rng = np.random.default_rng(seed_for(page_id, level, base_seed))
    width, height = page.size

    # Resolution: down to the level's dpi and back, so the geometry is the source's.
    factor = spec.dpi / SOURCE_DPI
    small = (max(1, round(width * factor)), max(1, round(height * factor)))
    page = page.resize(small, Image.Resampling.BILINEAR).resize(
        (width, height), Image.Resampling.BILINEAR
    )

    if spec.blur > 0:
        page = page.filter(ImageFilter.GaussianBlur(radius=spec.blur))

    if spec.skew > 0:
        angle = float(rng.uniform(-spec.skew, spec.skew))
        white = 255 if page.mode == "L" else (255, 255, 255)
        page = page.rotate(angle, resample=Image.Resampling.BICUBIC, expand=False, fillcolor=white)

    if spec.noise > 0:
        pixels = np.array(page)
        mask = rng.random((height, width)) < spec.noise
        salt = rng.random((height, width)) < 0.5
        pixels[mask & salt] = 255
        pixels[mask & ~salt] = 0
        page = Image.fromarray(pixels)

    if spec.jpeg_quality is not None:
        buffer = io.BytesIO()
        page.save(buffer, format="JPEG", quality=spec.jpeg_quality, optimize=False, subsampling=2)
        buffer.seek(0)
        with Image.open(buffer) as reread:
            page = reread.convert(page.mode)
    return page


def skew_angle(page_id: str, level: int, *, base_seed: int = BASE_SEED) -> float:
    """The degrees `degrade` turns a page by (counter-clockwise, about its centre) at a level:
    the first draw of the same generator, so a field's box on the clean page can be placed on
    the degraded one. The test suite holds it equal to what `degrade` does."""
    spec = LEVELS[level]
    if spec.skew <= 0:
        return 0.0
    rng = np.random.default_rng(seed_for(page_id, level, base_seed))
    return float(rng.uniform(-spec.skew, spec.skew))


def to_png(image: Image.Image) -> bytes:
    """PNG bytes with no metadata, so equal pixels are equal bytes."""
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=False, compress_level=6)
    return buffer.getvalue()
