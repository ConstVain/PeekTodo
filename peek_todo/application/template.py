"""Bundled Markdown templates for the new-document flow."""

from datetime import date
from pathlib import Path
from shutil import copyfile

from ..storage.paths import assets_dir

DEFAULT_TEMPLATE = assets_dir() / "template" / "Example-plan_simple.md"


def default_filename() -> str:
    return f"{date.today():%y%m%d}_目标与事项.md"


def write_template(template: Path, target: Path) -> None:
    """Copy the chosen template verbatim to the destination confirmed by the user."""
    copyfile(template, target)
