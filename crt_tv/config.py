import pathlib
import re
import textwrap
import tomllib
from typing import Literal, Self

import PIL.ImageColor
from loguru import logger
from pydantic import BaseModel, Field, field_validator

ASPECT_RATIO_REGEX = re.compile(r"^(?P<width>\d+):(?P<height>\d+)$")

PROJECT_ROOT = pathlib.Path(__file__).parent.parent
ASSETS_DIR = PROJECT_ROOT / "assets"

DEFAULT_FONTS: list[str | pathlib.Path] = [
    (ASSETS_DIR / "VCR_OSD_MONO_1.001.ttf"),
    "Courier New Bold.ttf",
    "Courier Bold.ttf",
    "FreeMonoBold.ttf",
]

# TODO: Clean up this mess:
#       seperate photo vs video vs common settings
#       remove the font, always use your own
#       font is different for photos vs videos


class TimestampConfig(BaseModel):
    position: Literal["top left", "top right", "bottom left", "bottom right"] = Field(
        default="bottom left",
        description="Position of the timestamp to be appended to the image",
    )

    failed_timestamp_extracts_dir: pathlib.Path | None = Field(
        default=None,
        description="A directory which will contain the cut parts of the images where the timestamp extraction failed",
    )
    date_format: str = "%-d %b %Y"  # e.g. 6 Nov 2024
    full_format: str = "%-d %b %Y %H:%M:%S"  # e.g. 6 Nov 2024 19:49:02
    fg_color: str = Field(
        default="white",
        description=(
            "Foreground color of the timestamp to be appended, can be a color name or a hex value, e.g. #FFFFFF"
        ),
    )
    bg_color: str = Field(
        default="black",
        description=(
            "Background color of the timestamp to be appended, can be a color name or a hex value, e.g. #FFFFFF"
        ),
    )
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
        description=textwrap.dedent(
            """
             List of fonts to use for the timestamp (the first match will be used)
             ref: https://pillow.readthedocs.io/en/stable/reference/ImageFont.html#PIL.ImageFont.truetype
        """
        ).strip(),
    )
    font_size: int = 80
    video_font_size: int = 48
    detect_timeout_seconds: int = 30
    video_max_attempts: int = 10

    @field_validator("failed_timestamp_extracts_dir")
    @classmethod
    def validate_failed_timestamp_extracts_dir(
        cls, value: pathlib.Path | None
    ) -> pathlib.Path | None:
        if value is None:
            return None

        if not value.is_absolute():
            raise ValueError(
                f"failed_timestamp_extracts_dir: Path must be absolute: {value}"
            )

        if not value.exists():
            logger.info(
                f"failed_timestamp_extracts_dir: Directory does not exist, creating: {value}"
            )
            value.mkdir(parents=True, exist_ok=True)
        elif not value.is_dir():
            raise ValueError(
                f"failed_timestamp_extracts_dir: Path is not a directory: {value}"
            )

        return value

    @property
    def fg_color_rgb(self) -> tuple[int, int, int] | tuple[int, int, int, int]:
        return PIL.ImageColor.getrgb(self.fg_color)

    @property
    def bg_color_rgb(self) -> tuple[int, int, int] | tuple[int, int, int, int]:
        return PIL.ImageColor.getrgb(self.bg_color)


class TimestampVideosConfig(BaseModel):
    position: Literal["top left", "top right", "bottom left", "bottom right"] = Field(
        default="bottom left",
        description="Position of the timestamp to be appended to the video",
    )
    margin_left: int = 0
    margin_right: int = 0
    margin_top: int = 0
    margin_bottom: int = 30
    padding_left: int = 80
    padding_right: int = 15
    padding_top: int = 15
    padding_bottom: int = 15


class VideosConfig(BaseModel):
    video_codec: str = "libx264"
    audio_codec: str = "aac"
    timestamp: TimestampVideosConfig = Field(default_factory=TimestampVideosConfig)


class Config(BaseModel):
    source_files_dir: pathlib.Path
    output_files_dir: pathlib.Path
    aspect_ratio: str
    resize_method: Literal["stretch", "crop"]
    timestamp: TimestampConfig = Field(default_factory=TimestampConfig)
    videos: VideosConfig = Field(default_factory=VideosConfig)

    @field_validator("source_files_dir")
    @classmethod
    def validate_source_files_dir(cls, value: pathlib.Path) -> pathlib.Path:
        if not value.is_absolute():
            raise ValueError(f"source_files_dir: Path must be absolute: {value}")

        if not value.exists():
            raise ValueError(f"source_files_dir: Directory does not exist: {value}")

        if not value.is_dir():
            raise ValueError(f"source_files_dir: Path is not a directory: {value}")

        return value

    @field_validator("output_files_dir")
    @classmethod
    def validate_output_files_dir(cls, value: pathlib.Path) -> pathlib.Path:
        if not value.is_absolute():
            raise ValueError(f"output_files_dir: Path must be absolute: {value}")

        if not value.exists():
            logger.info(
                f"output_files_dir: Directory does not exist, creating: {value}"
            )
            value.mkdir(parents=True, exist_ok=True)
        elif not value.is_dir():
            raise ValueError(f"output_files_dir: Path is not a directory: {value}")

        if not value.is_absolute():
            raise ValueError(f"output_files_dir: Path must be absolute: {value}")

        return value

    @field_validator("aspect_ratio")
    @classmethod
    def validate_aspect_ratio(cls, value: str) -> str:
        if not ASPECT_RATIO_REGEX.match(value):
            raise ValueError(
                f"Invalid aspect ratio '{value}', must be in the form 'width:height' (e.g. '4:3')"
            )

        return value

    @classmethod
    def load_from_file(cls, file_path: pathlib.Path) -> Self:
        with file_path.open("rb") as f:
            data = tomllib.load(f)

        return cls.model_validate(data)
