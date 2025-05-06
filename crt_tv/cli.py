import datetime
import pathlib
from typing import Annotated, TypedDict

import moviepy.editor as mp
import moviepy.video.fx.all as vfx
import typer
from loguru import logger
from PIL.Image import open as image_open

from crt_tv.config import Config
from crt_tv.fs_observer import observe_and_action_fs_events
from crt_tv.images import get_new_dimensions, process_single_image
from crt_tv.logging import configure_logging
from crt_tv.timestamp import (
    get_timestamp_font,
    parse_timestamp_from_image,
    parse_timestamp_from_video,
)
from crt_tv.utils import get_output_image_path


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
            image_timestamp = parse_timestamp_from_image(
                img, config, failed_timestamp_filename=file.name
            )
        except ValueError:
            logger.warning(f"No timestamp found in {file.name}")
            image_timestamp = None
        except RuntimeError as exc:
            logger.opt(exception=True).warning(
                f"Tesseract timed out while processing {file.name}"
            )
            raise typer.Exit(code=1) from exc

    logger.info(f"Timestamp found: {image_timestamp}")


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
def process_video(file: pathlib.Path) -> None:
    config = cli_state["config"]

    video = mp.VideoFileClip(str(file.resolve()))
    timestamp_clip = None

    try:
        timestamp = parse_timestamp_from_video(video, config, file)
    except Exception:
        logger.opt(exception=True).warning(
            f"Couldn't extract the timestamp from {file.name}, skipping adding it to the video",
        )
    else:
        if isinstance(timestamp, datetime.datetime):
            timestamp_text = timestamp.strftime(config.timestamp.full_format)
        elif isinstance(timestamp, datetime.date):
            logger.warning("Only date found in the video, using it as timestamp")
            timestamp_text = timestamp.strftime(config.timestamp.date_format)
        else:
            raise TypeError(
                f"timestamp must be a datetime.datetime or datetime.date instance, got {type(timestamp)}"
            )

        timestamp_clip = mp.TextClip(
            font=config.timestamp.font_names[0],
            txt=timestamp_text,
            fontsize=config.timestamp.video_font_size,
            color=config.timestamp.fg_color,
            bg_color=config.timestamp.bg_color,
        )

    orig_width, orig_height = video.size
    new_width, new_height = get_new_dimensions(
        orig_width=orig_width,
        orig_height=orig_height,
        new_aspect_ratio=config.aspect_ratio,
        resize_method=config.resize_method,
    )

    crop_x = (orig_width - new_width) // 2 if orig_width != new_width else 0
    crop_y = (orig_height - new_height) // 2 if orig_height != new_height else 0

    resized_video = vfx.crop(
        video,
        x1=crop_x,
        y1=crop_y,
        width=new_width,
        height=new_height,
    )

    if timestamp_clip is not None:
        y_pos, x_pos = config.timestamp.position.split(" ")

        resized_video = mp.CompositeVideoClip(
            [
                resized_video,
                timestamp_clip.set_duration(video.duration).set_pos(
                    (0, new_height - 80)
                ),
            ]
        )
    dest_path = get_output_image_path(file, config).resolve().with_suffix(".mp4")

    resized_video.write_videofile(
        str(dest_path),
        codec="libx264",
        audio_codec="aac",
    )

    logger.info(
        f"Processed video {file.name} to {dest_path.resolve()} with size {new_width}x{new_height}"
    )
