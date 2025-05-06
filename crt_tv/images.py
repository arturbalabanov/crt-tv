import datetime
import pathlib
from typing import Literal

from loguru import logger
from PIL.Image import Image
from PIL.Image import open as image_open
from PIL.ImageDraw import Draw
from PIL.ImageFont import FreeTypeFont

from crt_tv.config import Config
from crt_tv.resize import get_new_dimensions
from crt_tv.timestamp import parse_timestamp_from_image
from crt_tv.utils import get_output_path


def process_single_image(
    image_path: pathlib.Path, config: Config, timestamp_font: FreeTypeFont
) -> pathlib.Path:
    logger.info(f"Processing {image_path.name}")

    with image_open(image_path) as img:
        try:
            image_timestamp = parse_timestamp_from_image(
                img, config, failed_timestamp_filename=image_path.name
            )
        except ValueError:
            logger.warning(f"No timestamp found in {image_path.name}")
            image_timestamp = None
        except RuntimeError:
            logger.opt(exception=True).warning(
                f"Tesseract timed out while processing {image_path.name}"
            )
            image_timestamp = None

        resized_img = resize_image(
            img,
            new_aspect_ratio=config.aspect_ratio,
            resize_method=config.resize_method,
        )

        if image_timestamp is not None:
            draw_timestamp(
                resized_img,
                image_timestamp,
                font=timestamp_font,
                config=config,
            )

        output_image_path = get_output_path(image_path, config).resolve()
        resized_img.save(output_image_path)

    logger.info(f"Completed processing image {image_path.name}")

    return output_image_path


def resize_image(
    img: Image, new_aspect_ratio: str, *, resize_method: Literal["stretch", "crop"]
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


def draw_timestamp(
    img: Image,
    timestamp: datetime.datetime | datetime.date,
    *,
    font: FreeTypeFont,
    config: Config,
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

    draw = Draw(img)
    text_bbox_left, text_bbox_top, text_bbox_right, text_bbox_bottom = draw.textbbox(
        xy=(0, 0),
        text=timestamp_text,
        font=font,
    )

    text_width = text_bbox_right - text_bbox_left
    text_height = text_bbox_bottom - text_bbox_top

    left_x = 0
    right_x = int(
        img.width
        - text_width
        - config.timestamp.margin_left
        - config.timestamp.margin_right
        - config.timestamp.padding_left
        - config.timestamp.padding_right
    )
    top_y = 0
    bottom_y = int(
        img.height
        - text_height
        - config.timestamp.margin_top
        - config.timestamp.margin_bottom
        - config.timestamp.padding_top
        - config.timestamp.padding_bottom
    )

    match config.timestamp.position:
        case "top left":
            timestamp_x, timestamp_y = (left_x, top_y)
        case "top right":
            timestamp_x, timestamp_y = (right_x, top_y)
        case "bottom left":
            timestamp_x, timestamp_y = (left_x, bottom_y)
        case "bottom right":
            timestamp_x, timestamp_y = (right_x, bottom_y)
        case _:
            raise RuntimeError("invalid branch")

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
