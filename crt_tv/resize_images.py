import re
from typing import Literal

from PIL.Image import Image

ASPECT_RATIO_REGEX = re.compile(r"^(?P<width>\d+):(?P<height>\d+)$")


def get_new_dimensions(
    orig_width: int,
    orig_height: int,
    new_aspect_ratio: str,
    resize_method: Literal["stretch", "crop"],
) -> tuple[int, int]:
    aspect_ratio_match = ASPECT_RATIO_REGEX.match(new_aspect_ratio)

    if not aspect_ratio_match:
        raise ValueError(f"Invalid aspect ratio '{new_aspect_ratio}', must be in the form 'width:height'")

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
        raise ValueError(f"Invalid resize method '{resize_method}', must be 'stretch' or 'crop'")

    return new_width, new_height


def resize_image(img: Image, new_aspect_ratio: str, *, resize_method: Literal["stretch", "crop"]) -> Image:
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
        raise ValueError(f"Invalid resize method '{resize_method}', must be 'stretch' or 'crop'")
    return resized_img
