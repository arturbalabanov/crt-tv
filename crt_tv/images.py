import pathlib
from typing import Literal

from loguru import logger
from PIL.Image import Image
from PIL.Image import open as image_open
from PIL.ImageFont import FreeTypeFont

from crt_tv.config import ASPECT_RATIO_REGEX, Config
from crt_tv.timestamp import draw_timestamp, parse_timestamp_from_image
from crt_tv.utils import get_output_image_path


def process_single_image(
    image_path: pathlib.Path, config: Config, timestamp_font: FreeTypeFont
) -> pathlib.Path:
    logger.info(f"Processing {image_path.name}")

    with image_open(image_path) as img:
        try:
            image_timestamp = parse_timestamp_from_image(img, config, image_path)
        except ValueError:
            logger.warning(f"No timestamp found in {image_path.name}")
            image_timestamp = None
        except RuntimeError:
            logger.warning(
                f"Tesseract timed out while processing {image_path.name}", exc_info=True
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

        output_image_path = get_output_image_path(image_path, config).resolve()
        resized_img.save(output_image_path)

    logger.info(f"Completed processing image {image_path.name}")

    return output_image_path


# TODO: Move it to a seperate file as it's used for video as well
def get_new_dimensions(
    orig_width: int,
    orig_height: int,
    new_aspect_ratio: str,
    resize_method: Literal["stretch", "crop"],
) -> tuple[int, int]:
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
