import datetime
import pathlib
from typing import Annotated, TypedDict

import moviepy.editor as mp
import rich
import typer
from loguru import logger
from PIL.Image import open as image_open

from crt_tv.config import Config
from crt_tv.fs_observer import observe_and_action_fs_events
from crt_tv.images import process_single_image
from crt_tv.logging import configure_logging
from crt_tv.timestamp import (
    get_images_timestamp_font,
    parse_timestamp_from_image,
    parse_timestamp_from_video,
)
from crt_tv.video import process_single_video


class CLIState(TypedDict):
    verbose: bool
    config: Config


app = typer.Typer(
    name="crt-tv",
    help="A collection of scripts I'm running on a Raspberry Pi connected to a CRT TV",
)


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
        raise typer.BadParameter(
            f"--config-file: {config_file} is not an absolute path"
        )

    if not config_file.is_file():
        raise typer.BadParameter(f"--config-file: {config_file} is not a file")

    if config_file.suffix != ".toml":
        raise typer.BadParameter(
            f"--config-file: {config_file} is not a TOML file, must be .toml"
        )

    logger.info(f"Loading configuration from {config_file}")
    cli_state["config"] = Config.load_from_file(config_file)


@app.command()
def process(
    file_path: Annotated[
        pathlib.Path | None,
        typer.Argument(
            help="A file or directory to process, if not set all files in the source directory will be processed"
        ),
    ] = None,
) -> None:
    """Resize images and videos in the source directory to the specified aspect ratio and optionally add a timestamp"""

    config = cli_state["config"]
    timestamp_font = get_images_timestamp_font(config)

    if file_path is None:
        source_files_dir = config.source_files_dir
    elif file_path.is_dir():
        source_files_dir = file_path
    elif file_path.is_file():
        if file_path.suffix.lower() == ".jpg":
            process_single_image(file_path, config, timestamp_font)
        elif file_path.suffix.lower() == ".avi":
            process_single_video(file_path, config)
        else:
            logger.error(
                f"File {file_path.name} is not a supported format, suffix must be .jpg or .avi"
            )
            raise typer.Exit(code=1)

        return
    else:
        logger.error(f"File {file_path} is not a file or directory")
        raise typer.Exit(code=1)

    logger.info(
        f"Resizing files in {config.source_files_dir} to {config.aspect_ratio} aspect ratio "
        f"using {config.resize_method} method"
    )

    processed_images_count = 0
    processed_videos_count = 0

    for file_path in source_files_dir.glob("**/*"):
        if file_path.is_dir():
            continue

        if file_path.name.startswith("."):
            continue

        relative_file_path = file_path.relative_to(config.source_files_dir)
        output_file_path = config.output_files_dir / relative_file_path
        output_file_path.parent.mkdir(parents=True, exist_ok=True)

        if file_path.suffix.lower() == ".jpg":
            process_single_image(file_path, config, timestamp_font)
            processed_images_count += 1
        elif file_path.suffix.lower() == ".avi":
            process_single_video(file_path, config)
            processed_videos_count += 1
        else:
            logger.warning(
                f"File {file_path.name} is not a supported format, suffix must be .jpg or .avi, skipping"
            )

    logger.info(
        f"Processed {processed_images_count} images and {processed_videos_count} videos"
    )


@app.command()
def get_timestamp(file: pathlib.Path) -> None:
    """Get the timestamp from an image or video file"""

    config = cli_state["config"]

    logger.info(f"Getting timestamp from {file.name}")
    extracted_timestamp: datetime.datetime | datetime.date | None = None

    if file.suffix.lower() == ".jpg":
        logger.info(f"File {file.name} is an image")

        with image_open(file) as img:
            try:
                extracted_timestamp = parse_timestamp_from_image(
                    img, config, failed_timestamp_filename=file.name
                )
            except ValueError:
                logger.warning(f"No timestamp found in {file.name}")
            except RuntimeError as exc:
                logger.opt(exception=True).warning(
                    f"Tesseract timed out while processing {file.name}"
                )
                raise typer.Exit(code=1) from exc
    elif file.suffix.lower() == ".avi":
        logger.info(f"File {file.name} is a video")

        with mp.VideoFileClip(str(file.resolve())) as video:
            extracted_timestamp = parse_timestamp_from_video(
                video, config, video_file_path=file
            )
    else:
        logger.warning(
            f"File {file.name} is not a supported format, suffix must be .jpg or .avi"
        )
        raise typer.Exit(code=1)

    logger.info(f"Timestamp found: {extracted_timestamp}")


@app.command()
def run_observer(
    recursive: Annotated[
        bool,
        typer.Option(help="Should the observer check for files in nested directories"),
    ] = True,
    sleep_time: Annotated[
        float, typer.Option(help="How often (in seconds) to check for fs events")
    ] = 0.1,
) -> None:
    """Run the file system observer to automatically process images from the source directory"""

    config = cli_state["config"]

    logger.info(f"Running file system observer for {config.source_files_dir}")

    observe_and_action_fs_events(config, recursive=recursive, sleep_time=sleep_time)


@app.command()
def healthcheck():
    from moviepy.config import FFMPEG_BINARY, IMAGEMAGICK_BINARY, try_cmd

    success = True

    rich.print(f"[MoviePy] checking ffmpeg binary at {FFMPEG_BINARY}... ", end="")
    if try_cmd([FFMPEG_BINARY])[0]:
        rich.print("✅")
    else:
        rich.print("❌ (not found)")
        success = False

    rich.print(
        f"[MoviePy] checking ImageMagick binary at {IMAGEMAGICK_BINARY}... ", end=""
    )
    if try_cmd([IMAGEMAGICK_BINARY])[0]:
        rich.print("✅")
    else:
        rich.print("❌ (not found)")
        success = False

    raise typer.Exit(code=0 if success else 1)
