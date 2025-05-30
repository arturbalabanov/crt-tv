import datetime
import pathlib
import re

import moviepy.editor as mp
import pytesseract
from loguru import logger
from PIL.Image import Image
from PIL.Image import fromarray as image_fromarray
from PIL.ImageFont import FreeTypeFont, truetype

from crt_tv.config import Config

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


def parse_timestamp_from_image(
    img: Image,
    config: Config,
    *,
    failed_timestamp_filename: str,
) -> datetime.datetime | datetime.date:
    logger.debug("Cutting the bottom left corner of the image to extract the timestamp")

    img_width, img_height = img.size
    # TODO: Extract the magic numbers these into config options
    timestamp_region = img.crop((0, img_height - 100, 1000, img_height))

    logger.debug("Extracting all text from from the cut part of the image")

    extracted_text = pytesseract.image_to_string(
        timestamp_region, timeout=config.images.timestamp.detect_timeout_seconds
    )

    logger.debug(f"Extracted text: '{extracted_text}'")

    match = TIMESTAMP_PARSE_REGEX.search(extracted_text)

    failed_timestamp_extracts_dir = config.failed_timestamp_extracts_dir

    if failed_timestamp_extracts_dir and (not match or match.group("time") is None):
        timestamp_path = failed_timestamp_extracts_dir / failed_timestamp_filename
        relative_timestamp_path = timestamp_path.relative_to(failed_timestamp_extracts_dir.parent)

        logger.info(f"Couldn't extract the timestamp, saving the cut part of the image to {relative_timestamp_path}")

        failed_timestamp_extracts_dir.mkdir(parents=True, exist_ok=True)

        timestamp_region.save(timestamp_path.resolve())

        logger.info(f"Saved cut part of the image to {relative_timestamp_path}")

    if not match:
        logger.debug("No timestamp match was found in the image")
        raise ValueError("No datetime found in the image")

    year = int(match.group("year"))
    month = int(match.group("month"))
    day = int(match.group("day"))

    logger.debug(f"Date match was successful: {year=}, {month=}, {day=}")

    if match.group("time") is None:
        logger.debug("Couldn't extract the time compontents, using only the date")

        return datetime.date(year, month, day)

    hour = int(match.group("hour"))
    minute = int(match.group("minute"))
    second = int(match.group("second"))

    logger.debug(f"Time match was successful: {hour=}, {minute=}, {second=}")

    return datetime.datetime(year, month, day, hour, minute, second)


def parse_timestamp_from_video(
    video: mp.VideoFileClip,
    config: Config,
    video_file_path: pathlib.Path,
) -> datetime.datetime | datetime.date:
    logger.debug(f"Video dimensions: width={video.size[0]}, height={video.size[1]}")
    logger.debug(f"Total frames in video: {video.reader.nframes}")

    orig_width, orig_height = video.size
    total_frames = video.reader.nframes

    total_attempts = config.videos.timestamp.max_attempts
    logger.debug(f"Total attempts to extract timestamp: {total_attempts}")

    best_timestamp: datetime.datetime | datetime.date | None = None

    for attempt in range(0, total_attempts):
        frame_number = min(int((total_frames // total_attempts) * attempt), total_frames)
        frame_time = min(frame_number / video.fps, video.duration)

        logger.debug(
            f"Attempt {attempt + 1}/{total_attempts}: Extracting frame {frame_number} at time {frame_time:.2f}s"
        )

        img = image_fromarray(video.get_frame(frame_time))

        try:
            timestamp = parse_timestamp_from_image(
                img,
                config,
                failed_timestamp_filename=f"{video_file_path.stem}_frame_{frame_number}.jpg",
            )
            logger.debug(f"Timestamp successfully extracted: {timestamp}")
        except Exception:
            logger.warning(f"Failed to extract timestamp from frame {frame_number}")
            continue

        # NOTE: It's important to check for datetime first since datetime is a subclass of date

        if isinstance(timestamp, datetime.datetime):
            best_timestamp = timestamp
            logger.debug("Found a full datetime timestamp, stopping further attempts")
            break

        if isinstance(timestamp, datetime.date) and best_timestamp is not None:
            best_timestamp = timestamp
            logger.debug("Found a date-only timestamp, continuing to search for a full datetime")

    if best_timestamp is None:
        raise ValueError(f"No timestamp found in the video after {total_attempts} attempts")

    logger.info(f"Best timestamp extracted: {best_timestamp}")
    return best_timestamp


def get_images_timestamp_font(config: Config) -> FreeTypeFont:
    logger.info("Searching for timestamp font")

    for font_name in config.images.timestamp.font_names:
        try:
            font = truetype(font_name, config.images.timestamp.font_size)
        except OSError:
            logger.warning(f"Font '{font_name}' not found, trying next font")
        else:
            logger.info(f"Using timestamp font: {font_name}")
            return font

    raise OSError(f"None of the fonts {config.images.timestamp.font_names} were found")
