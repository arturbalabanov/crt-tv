import pathlib
import textwrap
import tomllib
from typing import Self

from pydantic import BaseModel, Field

PROJECT_ROOT = pathlib.Path(__file__).parent.parent
ASSETS_DIR = PROJECT_ROOT / "assets"

DEFAULT_FONTS: list[str | pathlib.Path] = [
    (ASSETS_DIR / "VCR_OSD_MONO_1.001.ttf"),
    "Courier New Bold.ttf",
    "Courier Bold.ttf",
    "FreeMonoBold.ttf",
]


class TimestampConfig(BaseModel):
    date_format: str = "%-d %b %Y"  # e.g. 6 Nov 2024
    full_format: str = "%-d %b %Y %H:%M:%S"  # e.g. 6 Nov 2024 19:49:02
    fg_color: str | tuple[int, int, int] = "white"
    bg_color: str | tuple[int, int, int] = "black"
    margin_left: int = 0
    margin_right: int = 0
    margin_top: int = 0
    margin_bottom: int = 30
    padding_left: int = 130
    padding_right: int = 100
    padding_top: int = 30
    padding_bottom: int = 30
    font_names: list[str | pathlib.Path] = Field(
        default_factory=lambda: DEFAULT_FONTS,
        description=textwrap.dedent("""
             List of fonts to use for the timestamp (the first match will be used)
             ref: https://pillow.readthedocs.io/en/stable/reference/ImageFont.html#PIL.ImageFont.truetype
        """).strip(),
    )
    font_size: int = 80
    detect_timeout_seconds: int = 30


class Config(BaseModel):
    timestamp: TimestampConfig = Field(default_factory=TimestampConfig)

    @classmethod
    def load_from_file(cls, file_path: pathlib.Path) -> Self:
        with file_path.open("rb") as f:
            data = tomllib.load(f)

        return cls.model_validate(data)
