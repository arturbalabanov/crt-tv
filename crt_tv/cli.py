import argparse
import pathlib
import sys

from loguru import logger
from PIL.Image import open as image_open
from PIL.ImageFont import FreeTypeFont

from crt_tv.config import Config
from crt_tv.resize_images import ASPECT_RATIO_REGEX, resize_image
from crt_tv.timestamp import draw_timestamp, get_timestamp_font, parse_timestamp_from_image


def parse_cli_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="crt-tv",
        description="Resize images into a different aspect ratio",
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


def validate_cli_args(args: argparse.Namespace) -> Config:
    if not args.input.exists():
        logger.error(f"Input file {args.input} is does not exist")
        sys.exit(1)

    if args.input.is_dir() and args.output.exists() and not args.output.is_dir():
        logger.error("Input is a directory but output is a file")
        sys.exit(1)

    if not ASPECT_RATIO_REGEX.match(args.aspect_ratio):
        logger.error(f"--aspect-ratio: Invalid aspect ratio '{args.aspect_ratio}', must be in the form 'width:height'")
        sys.exit(1)

    if args.config_file is None:
        config = Config()
        logger.info("Using default configuration values, use --config-file to set custom configuration values")
    else:
        if not args.config_file.is_file():
            logger.error(f"--config-file: {args.config_file} is not a file")
            sys.exit(1)

        if args.config_file.suffix != ".toml":
            logger.error(f"--config-file: {args.config_file} is not a TOML file, must be .toml")
            sys.exit(1)

        logger.info(f"Loading configuration from {args.config_file.resolve()}")
        config = Config.load_from_file(args.config_file)

    if args.failed_timestamp_extracts_dir is not None and not args.failed_timestamp_extracts_dir.is_dir():
        logger.error(f"--failed-timestamp-extracts-dir: {args.failed_timestamp_extracts_dir} is not a directory")
        sys.exit(1)

    return config


def process_single_file(
    image_path: pathlib.Path,
    args: argparse.Namespace,
    config: Config,
    timestamp_font: FreeTypeFont,
    output_image_path: pathlib.Path,
) -> None:
    logger.info(f"Processing {image_path.name}")

    with image_open(image_path) as img:
        try:
            image_timestamp = parse_timestamp_from_image(img, config, image_path, args.failed_timestamp_extracts_dir)
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


def main(args: argparse.Namespace, config: Config) -> None:
    images_str = "images in directory" if args.input.is_dir() else "image"

    logger.info(
        f"Resizing {images_str} {args.input} to {args.aspect_ratio} aspect ratio using {args.resize_method} method"
    )

    timestamp_font = get_timestamp_font(config)

    if args.input.is_file():
        if args.input.suffix.lower() != ".jpg":
            logger.error(f"Input file {args.input} is not a JPG file, only JPG files are supported")
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

            process_single_file(image_path, args, config, timestamp_font, output_image_path)

            processed_images_count += 1

        logger.info(f"Processed {processed_images_count} images")
    else:
        raise OSError(f"Input file {args.input} is not a file or directory")
