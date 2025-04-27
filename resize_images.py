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
import textwrap
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

ASSETS_DIR = pathlib.Path(__file__).parent / "assets"


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
    font_names: list[str | pathlib.Path] = pydantic.Field(
        default_factory=lambda: [
            (ASSETS_DIR / "VCR_OSD_MONO_1.001.ttf"),
            "Courier New Bold.ttf",
            "Courier Bold.ttf",
            "FreeMonoBold.ttf",
        ],
        description=textwrap.dedent("""
             List of fonts to use for the timestamp (the first match will be used)
             ref: https://pillow.readthedocs.io/en/stable/reference/ImageFont.html#PIL.ImageFont.truetype
        """).strip(),
    )
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
        "input",
        type=pathlib.Path,
        help="File or directory of files to process",
    )
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        help="The output path of the processed file (or directory if input is directory)",
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
    parser.add_argument(
        "--failed-timestamp-extracts-dir",
        type=pathlib.Path,
        help="A directory which will contain the cut parts of the images where the timestamp extraction failed",
        default=None,
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        dest="verbose",
        help="Enable DEBUG logs in the output",
        default=False,
    )
    return parser.parse_args()


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


def parse_timestamp_from_image(
    img: Image,
    config: ScriptConfig,
    failed_timestamp_extracts_dir: pathlib.Path | None,
) -> datetime.datetime | datetime.date:
    logger.debug("Cutting the bottom left corner of the image to extract the timestamp")

    img_width, img_height = img.size
    timestamp_region = img.crop((0, img_height - 100, 1000, img_height))

    logger.debug("Extracting all text from from the cut part of the image")

    extracted_text = pytesseract.image_to_string(
        timestamp_region, timeout=config.timestamp.detect_timeout_seconds
    )

    logger.debug(f"Extracted text: '{extracted_text}'")

    match = TIMESTAMP_PARSE_REGEX.search(extracted_text)

    if failed_timestamp_extracts_dir and (not match or match.group("time") is None):
        logger.debug(
            f"Couldn't extract the timestamp, saving the cut part of the image to {failed_timestamp_extracts_dir}"
        )

        failed_timestamp_extracts_dir.mkdir(parents=True, exist_ok=True)

        output_image_path = (
            failed_timestamp_extracts_dir / pathlib.Path(img.filename).name
        )
        timestamp_region.save(output_image_path)

        logger.info(f"Saved cut part of the image to {output_image_path}")

    if not match:
        logger.debug("No timestamp match was found in the image")
        raise ValueError("No datetime found in the image")

    year = int(match.group("year"))
    month = int(match.group("month"))
    day = int(match.group("day"))

    logger.debug(f"Date match was successful: {year=}, {month=}, {day=}")

    if match.group("time") is None:
        logger.debug("Couldn't extract the time compontents, using only the date")

        return datetime.date(year, month, day)

    hour = int(match.group("hour"))
    minute = int(match.group("minute"))
    second = int(match.group("second"))

    logger.debug(f"Time match was successful: {hour=}, {minute=}, {second=}")

    return datetime.datetime(year, month, day, hour, minute, second)


def draw_timestamp(
    img: Image,
    timestamp: datetime.datetime | datetime.date,
    *,
    position: Literal["top left", "top right", "bottom left", "bottom right"],
    font: ImageFont,
    config: ScriptConfig,
) -> None:
    # NOTE: It's important to check for datetime first since datetime is a subclass of date

    if isinstance(timestamp, datetime.datetime):
        timestamp_text = timestamp.strftime(config.timestamp.full_format)
    elif isinstance(timestamp, datetime.date):
        logger.warning("Only date found in the image, using it as timestamp")
        timestamp_text = timestamp.strftime(config.timestamp.date_format)
    else:
        raise TypeError(
            f"timestamp must be a datetime.datetime or datetime.date instance, got {type(timestamp)}"
        )

    draw = ImageDraw.Draw(img)
    text_bbox_left, text_bbox_top, text_bbox_right, text_bbox_bottom = draw.textbbox(
        xy=(0, 0),
        text=timestamp_text,
        font=font,
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
        font=font,
    )


def resize_image(
    img: Image,
    new_aspect_ratio: str,
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


def get_timestamp_font(config: ScriptConfig) -> ImageFont:
    logger.info("Searching for timestamp font")

    for font_name in config.timestamp.font_names:
        try:
            font = ImageFont.truetype(font_name, config.timestamp.font_size)
        except OSError:
            logger.warning(f"Font '{font_name}' not found, trying next font")
        else:
            logger.info(f"Using timestamp font: {font_name}")
            return font

    raise OSError(f"None of the fonts {config.timestamp.font_names} were found")


def process_single_file(
    image_path: pathlib.Path,
    args: argparse.Namespace,
    config: ScriptConfig,
    timestamp_font: ImageFont,
    output_image_path: pathlib.Path,
) -> None:
    logger.info(f"Processing {image_path.name}")

    with Image.open(image_path) as img:
        try:
            image_timestamp = parse_timestamp_from_image(
                img, config, args.failed_timestamp_extracts_dir
            )
        except ValueError:
            logger.warning(f"No timestamp found in {image_path.name}")
            image_timestamp = None
        except RuntimeError:
            logger.warning(f"Tesseract timed out while processing {image_path.name}")
            image_timestamp = None

        resized_img = resize_image(
            img,
            new_aspect_ratio=args.aspect_ratio,
            resize_method=args.resize_method,
        )

        if image_timestamp is not None:
            draw_timestamp(
                resized_img,
                image_timestamp,
                position=args.timestamp_position,
                font=timestamp_font,
                config=config,
            )

        resized_img.save(output_image_path.resolve())

        logger.info(f"Completed processing image {image_path.name}")


def main(args: argparse.Namespace, config: ScriptConfig) -> None:
    images_str = "images in directory" if args.input.is_dir() else "image"

    logger.info(
        f"Resizing {images_str} {args.input} to {args.aspect_ratio} aspect ratio "
        f"using {args.resize_method} method"
    )

    timestamp_font = get_timestamp_font(config)

    if args.input.is_file():
        if args.input.suffix.lower() != ".jpg":
            logger.error(
                f"Input file {args.input} is not a JPG file, only JPG files are supported"
            )
            sys.exit(1)

        if args.output.is_dir():
            output_file_path = args.output / args.input.name
        else:
            output_file_path = args.output

        process_single_file(args.input, args, config, timestamp_font, output_file_path)
    elif args.input.is_dir():
        processed_images_count = 0

        for image_path in args.input.glob("**/*.[jJ][pP][gG]"):
            relative_image_path = image_path.relative_to(args.input)

            output_image_path = args.output / relative_image_path
            output_image_path.parent.mkdir(parents=True, exist_ok=True)

            process_single_file(
                image_path, args, config, timestamp_font, output_image_path
            )

            processed_images_count += 1

        logger.info(f"Processed {processed_images_count} images")
    else:
        raise OSError(f"Input file {args.input} is not a file or directory")


def configure_logging(stdout_level: str = "INFO") -> None:
    logger.remove()  # remove the default hanlder
    logger.add(
        sys.stdout,
        colorize=True,
        level=stdout_level,
        format="<level>{level}</level> {message}",
    )


if __name__ == "__main__":
    args = parse_cli_args()

    configure_logging(
        stdout_level="DEBUG" if args.verbose else "INFO",
    )

    if not args.input.exists():
        logger.error(f"Input file {args.input} is does not exist")
        sys.exit(1)

    if args.input.is_dir() and args.output.exists() and not args.output.is_dir():
        logger.error("Input is a directory but output is a file")
        sys.exit(1)

    if not ASPECT_RATIO_REGEX.match(args.aspect_ratio):
        logger.error(
            f"--aspect-ratio: Invalid aspect ratio '{args.aspect_ratio}', must be in the form 'width:height'"
        )
        sys.exit(1)

    if args.config_file is None:
        config = ScriptConfig()
        logger.info(
            "Using default configuration values, use --config-file to set custom configuration values"
        )
    else:
        if not args.config_file.is_file():
            logger.error(f"--config-file: {args.config_file} is not a file")
            sys.exit(1)

        if args.config_file.suffix != ".toml":
            logger.error(
                f"--config-file: {args.config_file} is not a TOML file, must be .toml"
            )
            sys.exit(1)

        logger.info(f"Loading configuration from {args.config_file.resolve()}")
        config = ScriptConfig.load_from_file(args.config_file)

    if (
        args.failed_timestamp_extracts_dir is not None
        and not args.failed_timestamp_extracts_dir.is_dir()
    ):
        logger.error(
            f"--failed-timestamp-extracts-dir: {args.failed_timestamp_extracts_dir} is not a directory"
        )
        sys.exit(1)

    try:
        main(args, config)
    except KeyboardInterrupt:
        logger.warning(
            "Process interrupted by user, partial results may be present in the output"
        )
        sys.exit(130)
