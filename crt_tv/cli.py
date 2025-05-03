import pathlib
from typing import Annotated, TypedDict

import typer
from loguru import logger
from PIL.Image import open as image_open

from crt_tv.config import Config
from crt_tv.fs_observer import observe_and_action_fs_events
from crt_tv.images import process_single_image
from crt_tv.logging import configure_logging
from crt_tv.timestamp import get_timestamp_font, parse_timestamp_from_image


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
            default_factory=lambda: pathlib.Path.home() / ".config" / "crt-tv.toml",
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
        raise typer.BadParameter(f"--config-file: {config_file} is not an absolute path")

    if not config_file.is_file():
        raise typer.BadParameter(f"--config-file: {config_file} is not a file")

    if config_file.suffix != ".toml":
        raise typer.BadParameter(f"--config-file: {config_file} is not a TOML file, must be .toml")

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

        process_single_image(image_path, config, timestamp_font)

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


@app.command()
def run_observer(
    recursive: Annotated[bool, typer.Option(help="Should the observer check for files in nested directories")] = True,
    sleep_time: Annotated[float, typer.Option(help="How often (in seconds) to check for fs events")] = 0.1,
) -> None:
    """Run the file system observer to automatically process images from the source directory"""

    config = cli_state["config"]

    logger.info(f"Running file system observer for {config.source_files_dir}")

    observe_and_action_fs_events(config, recursive=True)
