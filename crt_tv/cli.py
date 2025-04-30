import pathlib
from typing import Annotated, TypedDict

import typer
from loguru import logger
from PIL.Image import open as image_open
from PIL.ImageFont import FreeTypeFont

from crt_tv.config import Config
from crt_tv.logging import configure_logging
from crt_tv.resize_images import resize_image
from crt_tv.timestamp import draw_timestamp, get_timestamp_font, parse_timestamp_from_image
from crt_tv.utils import get_output_image_path


def process_single_file(image_path: pathlib.Path, config: Config, timestamp_font: FreeTypeFont) -> pathlib.Path:
    logger.info(f"Processing {image_path.name}")

    with image_open(image_path) as img:
        try:
            image_timestamp = parse_timestamp_from_image(img, config, image_path)
        except ValueError:
            logger.warning(f"No timestamp found in {image_path.name}")
            image_timestamp = None
        except RuntimeError:
            logger.warning(f"Tesseract timed out while processing {image_path.name}", exc_info=True)
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


class CLIState(TypedDict):
    verbose: bool
    config: Config


app = typer.Typer(name="crt-tv", help="A collection of scripts I'm running on a Raspberry Pi connected to a CRT TV")


cli_state: CLIState = {
    "verbose": False,
    "config": None,  # type: ignore[typeddict-item]
}


@app.callback()
def main(
    config_file: Annotated[
        pathlib.Path,
        typer.Option(
            "-c",
            "--config-file",
            help="Path to the configuration file (in TOML format)",
        ),
    ],
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            "-v",
            help="Enable DEBUG logs in the output",
            is_eager=True,
        ),
    ] = False,
) -> None:
    if verbose:
        cli_state["verbose"] = True

    configure_logging(stdout_level="DEBUG" if verbose else "INFO")

    if not config_file.is_absolute():
        raise typer.BadParameter(f"{config_file} is not an absolute path", param=config_file)

    if not config_file.is_file():
        raise typer.BadParameter(f"{config_file} is not a file", param=config_file)

    if config_file.suffix != ".toml":
        raise typer.BadParameter(f"{config_file} is not a TOML file, must be .toml", param=config_file)

    logger.info(f"Loading configuration from {config_file}")
    cli_state["config"] = Config.load_from_file(config_file)


@app.command()
def process_images() -> None:
    """Resize images in the source directory to the specified aspect ratio and optionally add a timestamp"""

    config = cli_state["config"]

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

        process_single_file(image_path, config, timestamp_font)

        processed_images_count += 1

    logger.info(f"Processed {processed_images_count} images")


@app.command()
def get_timestamp(file: pathlib.Path) -> None:
    """Get the timestamp from an image"""

    config = cli_state["config"]

    logger.info(f"Getting timestamp from {file.name}")

    with image_open(file) as img:
        try:
            image_timestamp = parse_timestamp_from_image(img, config, file)
        except ValueError:
            logger.warning(f"No timestamp found in {file.name}")
            image_timestamp = None
        except RuntimeError as exc:
            logger.warning(f"Tesseract timed out while processing {file.name}", exc_info=True)
            raise typer.Exit(code=1) from exc

    logger.info(f"Timestamp found: {image_timestamp}")
