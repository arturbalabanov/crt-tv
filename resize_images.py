# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "pillow==11.2.1",
#     "pytesseract==0.3.13",
# ]
# ///

import pathlib
import argparse
import sys
import re
from typing import Literal, Union
import datetime

import pytesseract  # type: ignore[import-not-found]
from PIL import Image, ImageDraw, ImageFont  # type: ignore[import-untyped]

# TODO: Use logging instead of prints

# TODO: Add automatic image rotation
#       Exif data is not present for these files but a simple check could be
#       to rotate clockwise until the timestamp is found
#       Actually, this doesn't work as the timestamp is alwaus horizonal...

# TODO: Clean the output dir before the run in case we removed files from source dir

# TODO: Only search the bottom part of the image for the timestamp


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

TIMESTAMP_DATE_FORMAT = "%-d %b %Y"  # e.g. 6 Nov 2024
TIMESTAMP_FULL_FORMAT = f"{TIMESTAMP_DATE_FORMAT} %H:%M:%S"  # e.g. 6 Nov 2024 19:49:02
TIMESTAMP_FG_COLOR = "white"
TIMESTAMP_BG_COLOR = "black"
TIMESTAMP_MARGIN_LEFT = 0
TIMESTAMP_MARGIN_RIGHT = 0
TIMESTAMP_MARGIN_TOP = 0
TIMESTAMP_MARGIN_BOTTOM = 30
TIMESTAMP_PADDING_LEFT = 100
TIMESTAMP_PADDING_RIGHT = 100
TIMESTAMP_PADDING_TOP = 30
TIMESTAMP_PADDING_BOTTOM = 30
# ref: https://pillow.readthedocs.io/en/stable/reference/ImageFont.html#PIL.ImageFont.truetype
TIMESTAMP_FONT_NAME = "Arial Unicode.ttf"
TIMESTAMP_FONT_SIZE = 80
TIMESTAMP_DETECT_TIMEOUT_SECONDS = 5


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
    args = parser.parse_args()

    if not args.input_dir.is_dir():
        print(f"ERROR --input-dir: {args.input_dir} is not a directory")
        sys.exit(1)

    if not args.output_dir.is_dir():
        print(f"ERROR --output-dir: {args.output_dir} is not a directory")
        sys.exit(1)

    if not ASPECT_RATIO_REGEX.match(args.aspect_ratio):
        print(
            f"ERROR --aspect-ratio: Invalid aspect ratio '{args.aspect_ratio}', must be in the form 'width:height'"
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


def parse_timestamp_from_image(img: Image) -> Union[datetime.datetime, datetime.date]:
    datetime_text = pytesseract.image_to_string(
        img, timeout=TIMESTAMP_DETECT_TIMEOUT_SECONDS
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
    timestamp: Union[datetime.datetime, datetime.date],
    *,
    position: Literal["top left", "top right", "bottom left", "bottom right"],
) -> None:
    timestamp_font = ImageFont.truetype(TIMESTAMP_FONT_NAME, TIMESTAMP_FONT_SIZE)

    if isinstance(timestamp, datetime.date):
        timestamp_text = timestamp.strftime(TIMESTAMP_DATE_FORMAT)
    elif isinstance(timestamp, datetime.datetime):
        timestamp_text = timestamp.strftime(TIMESTAMP_FULL_FORMAT)
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
        - TIMESTAMP_MARGIN_LEFT
        - TIMESTAMP_MARGIN_RIGHT
        - TIMESTAMP_PADDING_LEFT
        - TIMESTAMP_PADDING_RIGHT
    )
    top_y = 0
    bottom_y = (
        img.height
        - text_height
        - TIMESTAMP_MARGIN_TOP
        - TIMESTAMP_MARGIN_BOTTOM
        - TIMESTAMP_PADDING_TOP
        - TIMESTAMP_PADDING_BOTTOM
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

    bg_rect_left = timestamp_x + TIMESTAMP_MARGIN_LEFT
    bg_rect_top = timestamp_y + TIMESTAMP_MARGIN_TOP
    bg_rect_right = (
        bg_rect_left + TIMESTAMP_PADDING_LEFT + text_width + TIMESTAMP_PADDING_RIGHT
    )
    bg_rect_bottom = (
        bg_rect_top + TIMESTAMP_PADDING_TOP + text_height + TIMESTAMP_PADDING_BOTTOM
    )

    text_x = bg_rect_left + TIMESTAMP_PADDING_LEFT
    text_y = bg_rect_top - text_bbox_top + TIMESTAMP_PADDING_TOP

    draw.rectangle(
        (bg_rect_left, bg_rect_top, bg_rect_right, bg_rect_bottom),
        fill=TIMESTAMP_BG_COLOR,
    )
    draw.text(
        xy=(text_x, text_y),
        text=timestamp_text,
        fill=TIMESTAMP_FG_COLOR,
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


def main(args: argparse.Namespace) -> None:
    processed_images_count = 0

    print(
        f"Resizing images in {args.input_dir} to {args.aspect_ratio} aspect ratio "
        f"using {args.resize_method} method"
    )

    for image_path in args.input_dir.glob("**/*.[jJ][pP][gG]"):
        relative_image_path = image_path.relative_to(args.input_dir)

        print(f"Processing {relative_image_path}")

        with Image.open(image_path) as img:
            try:
                image_timestamp = parse_timestamp_from_image(img)
            except ValueError:
                print(f"WARNING: No timestamp found in {relative_image_path}")
                image_timestamp = None

            resized_img = resize_image(
                img,
                new_aspect_ratio=args.aspect_ratio,
                output_dir=args.output_dir,
                resize_method=args.resize_method,
            )

            if image_timestamp is not None:
                if isinstance(image_timestamp, datetime.date):
                    print(
                        f"WARNING: Only date found in {relative_image_path}, using it as timestamp"
                    )

                draw_timestamp(
                    resized_img,
                    image_timestamp,
                    position=args.timestamp_position,
                )

            output_image_path = args.output_dir / relative_image_path
            output_image_path.parent.mkdir(parents=True, exist_ok=True)
            resized_img.save(output_image_path.resolve())

            print(f"Completed resizing image {relative_image_path}")
            processed_images_count += 1

    print()
    print(f"Processed {processed_images_count} images")


if __name__ == "__main__":
    args = parse_cli_args()
    main(args)
