# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#     "loguru==0.7.3",
#     "pillow==11.2.1",
#     "pydantic==2.11.3",
#     "pytesseract==0.3.13",
# ]
# ///

import pathlib
import argparse
import sys
import tomllib
import re
from typing import Literal, Self
import datetime

import pydantic  # type: ignore[import-not-found]
import pytesseract  # type: ignore[import-not-found]
from PIL import Image, ImageDraw, ImageFont  # type: ignore[import-untyped]
from loguru import logger  # type: ignore[import-not-found]

# TODO: Add automatic image rotation
#       Exif data is not present for these files but a simple check could be
#       to rotate clockwise until the timestamp is found
#       Actually, this doesn't work as the timestamp is alwaus horizonal...

# TODO: Clean the output dir before the run in case we removed files from source dir
#       Actually, this script takes long time to run on the Raspberry Pi, especially
#       with a big library, so instead it should have a flag to re-generate all pictures
#       (in which case, remove the output dir) and instead generate only for new pictures
#       and remove previously processed ones which are not found in the source dir anymore


# TODO: Only search the bottom part of the image for the timestamp

# TODO: Add support for videos


ASPECT_RATIO_REGEX = re.compile(r"^(?P<width>\d+):(?P<height>\d+)$")

# The timestamp from the image, e.g. 2024/11/06 19:49:09
# Sometimes only part of it is visivle against the background, in which case
# as long as the date is visible, it's good enough to use it
TIMESTAMP_PARSE_REGEX = re.compile(
    r"""
        (?P<year>\d{4})            # Match the year
        \s*/\s*                    # Followed by /
        (?P<month>\d{2})           # Match the month
        \s*/\s*                    # Followed by /
        (?P<day>\d{2})             # Match the day
        (?P<time>                  # Optionally, match the time
            \s+
            (?P<hour>\d{2})        # Match the hour
            \s*:\s*                # Followed by :
            (?P<minute>\d{2})      # Match the minute
            \s*:\s*                # Followed by :
            (?P<second>\d{2})      # Match the second
        )?
    """,
    re.VERBOSE,
)


class TimestampConfig(pydantic.BaseModel):
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
    # TODO: Convert to a list of fonts
    # ref: https://pillow.readthedocs.io/en/stable/reference/ImageFont.html#PIL.ImageFont.truetype
    font_name: str = "Arial Unicode.ttf"
    fallback_font_name: str = "FreeSans.ttf"
    font_size: int = 80
    detect_timeout_seconds: int = 30


class ScriptConfig(pydantic.BaseModel):
    timestamp: TimestampConfig = pydantic.Field(default_factory=TimestampConfig)

    @classmethod
    def load_from_file(cls, file_path: pathlib.Path) -> Self:
        with file_path.open("rb") as f:
            data = tomllib.load(f)

        return cls.model_validate(data)


def parse_cli_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Resize images into a different aspect ratio"
    )
    parser.add_argument(
        "--input-dir",
        type=pathlib.Path,
        help="Directory containing the original files",
        required=True,
    )
    parser.add_argument(
        "--output-dir",
        type=pathlib.Path,
        help="The output directory for the processed playlist",
        required=True,
    )
    parser.add_argument(
        "--aspect-ratio",
        type=str,
        default="4:3",
        help="The new aspect ratio of the processed files",
    )
    parser.add_argument(
        "--resize-method",
        type=str,
        choices=["stretch", "crop"],
        help="Resize method to use",
        required=True,
    )
    parser.add_argument(
        "--timestamp-position",
        type=str,
        choices=["top left", "top right", "bottom left", "bottom right"],
        help="Position of the timestamp on the image",
        required=True,
    )
    parser.add_argument(
        "--config-file",
        type=pathlib.Path,
        help="Path to the configuration file (in TOML format) if not using the default values",
        default=None,
    )
    args = parser.parse_args()

    if not args.input_dir.is_dir():
        logger.error(f"--input-dir: {args.input_dir} is not a directory")
        sys.exit(1)

    if not args.output_dir.is_dir():
        logger.error(f"--output-dir: {args.output_dir} is not a directory")
        sys.exit(1)

    if not ASPECT_RATIO_REGEX.match(args.aspect_ratio):
        logger.error(
            f"--aspect-ratio: Invalid aspect ratio '{args.aspect_ratio}', must be in the form 'width:height'"
        )
        sys.exit(1)

    if args.config_file is not None:
        if not args.config_file.is_file():
            logger.error(f"--config-file: {args.config_file} is not a file")
            sys.exit(1)

        if args.config_file.suffix != ".toml":
            logger.error(
                f"--config-file: {args.config_file} is not a TOML file, must be .toml"
            )
            sys.exit(1)

    return args


def get_new_dimensions(
    orig_width: int,
    orig_height: int,
    new_aspect_ratio: str,
    resize_method: Literal["stretch", "crop"],
):
    aspect_ratio_match = ASPECT_RATIO_REGEX.match(new_aspect_ratio)

    if not aspect_ratio_match:
        raise ValueError(
            f"Invalid aspect ratio '{new_aspect_ratio}', must be in the form 'width:height'"
        )

    aspect_ratio_width = int(aspect_ratio_match.group("width"))
    aspect_ratio_height = int(aspect_ratio_match.group("height"))
    aspect_ratio = aspect_ratio_width / aspect_ratio_height

    if resize_method == "stretch":
        new_width = orig_width
        new_height = int(orig_width / aspect_ratio)
    elif resize_method == "crop":
        new_height = orig_height
        new_width = int(orig_height * aspect_ratio)

        if new_width > orig_width:
            new_width = orig_width
            new_height = int(orig_width / aspect_ratio)
    else:
        raise ValueError(
            f"Invalid resize method '{resize_method}', must be 'stretch' or 'crop'"
        )

    return new_width, new_height


def parse_timestamp_from_image(img: Image) -> datetime.datetime | datetime.date:
    datetime_text = pytesseract.image_to_string(
        img, timeout=config.timestamp.detect_timeout_seconds
    )
    match = TIMESTAMP_PARSE_REGEX.search(datetime_text)

    if not match:
        raise ValueError("No datetime found in the image")

    year = int(match.group("year"))
    month = int(match.group("month"))
    day = int(match.group("day"))

    if match.group("time") is None:
        return datetime.date(year, month, day)

    hour = int(match.group("hour"))
    minute = int(match.group("minute"))
    second = int(match.group("second"))

    return datetime.datetime(year, month, day, hour, minute, second)


def draw_timestamp(
    img: Image,
    timestamp: datetime.datetime | datetime.date,
    *,
    position: Literal["top left", "top right", "bottom left", "bottom right"],
) -> None:
    try:
        timestamp_font = ImageFont.truetype(
            config.timestamp.font_name, config.timestamp.font_size
        )
    except OSError:
        timestamp_font = ImageFont.truetype(
            config.timestamp.fallback_font_name, config.timestamp.font_size
        )

    if isinstance(timestamp, datetime.date):
        timestamp_text = timestamp.strftime(config.timestamp.date_format)
    elif isinstance(timestamp, datetime.datetime):
        timestamp_text = timestamp.strftime(config.timestamp.full_format)
    else:
        raise TypeError(
            f"timestamp must be a datetime.datetime or datetime.date instance, got {type(timestamp)}"
        )

    draw = ImageDraw.Draw(img)
    text_bbox_left, text_bbox_top, text_bbox_right, text_bbox_bottom = draw.textbbox(
        xy=(0, 0),
        text=timestamp_text,
        font=timestamp_font,
    )

    text_width = text_bbox_right - text_bbox_left
    text_height = text_bbox_bottom - text_bbox_top

    left_x = 0
    right_x = (
        img.width
        - text_width
        - config.timestamp.margin_left
        - config.timestamp.margin_right
        - config.timestamp.padding_left
        - config.timestamp.padding_right
    )
    top_y = 0
    bottom_y = (
        img.height
        - text_height
        - config.timestamp.margin_top
        - config.timestamp.margin_bottom
        - config.timestamp.padding_top
        - config.timestamp.padding_bottom
    )

    if position == "top left":
        timestamp_x, timestamp_y = (left_x, top_y)
    elif position == "top right":
        timestamp_x, timestamp_y = (right_x, top_y)
    elif position == "bottom left":
        timestamp_x, timestamp_y = (left_x, bottom_y)
    elif position == "bottom right":
        timestamp_x, timestamp_y = (right_x, bottom_y)
    else:
        raise ValueError(
            f"Invalid position '{position}', must be 'top left', 'top right', 'bottom left', or 'bottom right'"
        )

    bg_rect_left = timestamp_x + config.timestamp.margin_left
    bg_rect_top = timestamp_y + config.timestamp.margin_top
    bg_rect_right = (
        bg_rect_left
        + config.timestamp.padding_left
        + text_width
        + config.timestamp.padding_right
    )
    bg_rect_bottom = (
        bg_rect_top
        + config.timestamp.padding_top
        + text_height
        + config.timestamp.padding_bottom
    )

    text_x = bg_rect_left + config.timestamp.padding_left
    text_y = bg_rect_top - text_bbox_top + config.timestamp.padding_top

    draw.rectangle(
        (bg_rect_left, bg_rect_top, bg_rect_right, bg_rect_bottom),
        fill=config.timestamp.bg_color,
    )
    draw.text(
        xy=(text_x, text_y),
        text=timestamp_text,
        fill=config.timestamp.fg_color,
        font=timestamp_font,
    )


def resize_image(
    img: Image,
    new_aspect_ratio: str,
    output_dir: pathlib.Path,
    *,
    resize_method: Literal["stretch", "crop"],
) -> Image:
    orig_width, orig_height = img.size

    new_width, new_height = get_new_dimensions(
        orig_width,
        orig_height,
        new_aspect_ratio,
        resize_method=resize_method,
    )

    if resize_method == "stretch":
        resized_img = img.resize((new_width, new_height))
    elif resize_method == "crop":
        left = (orig_width - new_width) // 2
        top = (orig_height - new_height) // 2
        right = (orig_width + new_width) // 2
        bottom = (orig_height + new_height) // 2

        resized_img = img.crop((left, top, right, bottom))
    else:
        raise ValueError(
            f"Invalid resize method '{resize_method}', must be 'stretch' or 'crop'"
        )
    return resized_img


def main(args: argparse.Namespace, config: ScriptConfig) -> None:
    processed_images_count = 0

    logger.info(
        f"Resizing images in {args.input_dir} to {args.aspect_ratio} aspect ratio "
        f"using {args.resize_method} method"
    )

    for image_path in args.input_dir.glob("**/*.[jJ][pP][gG]"):
        relative_image_path = image_path.relative_to(args.input_dir)

        logger.info(f"Processing {relative_image_path}")

        with Image.open(image_path) as img:
            try:
                image_timestamp = parse_timestamp_from_image(img)
            except ValueError:
                logger.warning(f"No timestamp found in {relative_image_path}")
                image_timestamp = None
            except RuntimeError:
                logger.warning(
                    f"Tesseract timed out while processing {relative_image_path}"
                )
                image_timestamp = None

            resized_img = resize_image(
                img,
                new_aspect_ratio=args.aspect_ratio,
                output_dir=args.output_dir,
                resize_method=args.resize_method,
            )

            if image_timestamp is not None:
                if isinstance(image_timestamp, datetime.date):
                    logger.warning(
                        f"Only date found in {relative_image_path}, using it as timestamp"
                    )

                draw_timestamp(
                    resized_img,
                    image_timestamp,
                    position=args.timestamp_position,
                )

            output_image_path = args.output_dir / relative_image_path
            output_image_path.parent.mkdir(parents=True, exist_ok=True)
            resized_img.save(output_image_path.resolve())

            logger.info(f"Completed resizing image {relative_image_path}")
            processed_images_count += 1

    logger.info(f"Processed {processed_images_count} images")


def configure_logging() -> None:
    logger.remove()  # remove the default hanlder
    logger.add(
        sys.stdout,
        colorize=True,
        format="<level>{level}</level> {message}",
    )


if __name__ == "__main__":
    configure_logging()
    args = parse_cli_args()

    if args.config_file is None:
        config = ScriptConfig()
        logger.info(
            "Using default configuration values, use --config-file to set custom configuration values"
        )
    else:
        logger.info(f"Loading configuration from {args.config_file.resolve()}")
        config = ScriptConfig.load_from_file(args.config_file)

    try:
        main(args, config)
    except KeyboardInterrupt:
        logger.warning(
            "Process interrupted by user, partial results may be present in the output directory"
        )
        sys.exit(130)
