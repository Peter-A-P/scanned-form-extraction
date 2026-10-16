"""legible: the command line. Commands are added as the stages they run are built."""

from __future__ import annotations

from pathlib import Path

import typer
from PIL import Image

from legible import __version__
from legible.degrade import LEVELS, degrade, to_png

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.callback()
def _root() -> None:
    """Forms That Read Themselves."""


@app.command()
def version() -> None:
    """Print the package version."""
    typer.echo(__version__)


@app.command("degrade")
def degrade_page(
    page: Path = typer.Argument(..., exists=True, dir_okay=False, help="A 300 dpi page image."),
    out: Path = typer.Argument(..., help="Where to write the degraded PNG."),
    level: int = typer.Option(..., min=0, max=len(LEVELS) - 1, help="Degradation level, 0 to 4."),
    page_id: str = typer.Option(..., help="The page's manifest id; it seeds the random draws."),
) -> None:
    """Degrade one page to a level, reproducibly."""
    with Image.open(page) as image:
        out.write_bytes(to_png(degrade(image, page_id, level)))


def main() -> None:
    app()
