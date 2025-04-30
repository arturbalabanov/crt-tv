import argparse
import pathlib
import sys

from loguru import logger
from PIL.Image import open as image_open
from PIL.ImageFont import FreeTypeFont

from crt_tv.config import Config
from crt_tv.resize_images import resize_image
from crt_tv.timestamp import draw_timestamp, get_timestamp_font, parse_timestamp_from_image


def parse_cli_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="crt-tv",
        description="Resize images into a different aspect ratio",
    )
    parser.add_argument(
        "--config-file",
        type=pathlib.Path,
        help="Path to the configuration file (in TOML format) if not using the default values",
        required=True,
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


def get_config(config_file_path: pathlib.Path) -> Config:
    if not config_file_path.is_absolute():
        logger.error(f"--config-file: {config_file_path} is not an absolute path")
        sys.exit(1)

    if not config_file_path.is_file():
        logger.error(f"--config-file: {config_file_path} is not a file")
        sys.exit(1)

    if config_file_path.suffix != ".toml":
        logger.error(f"--config-file: {config_file_path} is not a TOML file, must be .toml")
        sys.exit(1)

    logger.info(f"Loading configuration from {config_file_path.resolve()}")
    return Config.load_from_file(config_file_path)


def process_single_file(
    image_path: pathlib.Path,
    config: Config,
    timestamp_font: FreeTypeFont,
    output_image_path: pathlib.Path,
) -> None:
    logger.info(f"Processing {image_path.name}")

    with image_open(image_path) as img:
        try:
            image_timestamp = parse_timestamp_from_image(img, config, image_path)
        except ValueError:
            logger.warning(f"No timestamp found in {image_path.name}")
            image_timestamp = None
        except RuntimeError:
            logger.warning(f"Tesseract timed out while processing {image_path.name}")
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

        resized_img.save(output_image_path.resolve())

        logger.info(f"Completed processing image {image_path.name}")


def main(config: Config) -> None:
    logger.info(
        f"Resizing images in {config.source_files_dir} to {config.aspect_ratio} aspect ratio "
        f"using {config.resize_method} method"
    )

    timestamp_font = get_timestamp_font(config)

    processed_images_count = 0

    for image_path in config.source_files_dir.glob("**/*.[jJ][pP][gG]"):
        relative_image_path = image_path.relative_to(config.source_files_dir)

        output_image_path = config.output_files_dir / relative_image_path
        output_image_path.parent.mkdir(parents=True, exist_ok=True)

        process_single_file(image_path, config, timestamp_font, output_image_path)

        processed_images_count += 1

    logger.info(f"Processed {processed_images_count} images")
