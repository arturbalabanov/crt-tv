import datetime
import pathlib

import moviepy.editor as mp
import moviepy.video.fx.all as vfx
from loguru import logger

from crt_tv.config import Config
from crt_tv.resize import get_new_dimensions
from crt_tv.timestamp import parse_timestamp_from_video
from crt_tv.utils import get_output_path


def process_single_video(
    video_path: pathlib.Path,
    config: Config,
) -> pathlib.Path:
    with mp.VideoFileClip(str(video_path.resolve())) as video:
        timestamp_clip = None

        try:
            timestamp = parse_timestamp_from_video(video, config, video_path)
        except Exception:
            logger.opt(exception=True).warning(
                f"Couldn't extract the timestamp from {video_path.name}, skipping adding it to the video",
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
                        # TODO: Extract these numbers into config options
                        # TODO: Take into account the timestamp position
                        (0, new_height - 80)
                    ),
                ]
            )
        dest_path = get_output_path(video_path, config)

        resized_video.write_videofile(
            str(dest_path.resolve()),
            codec=config.videos.video_codec,
            audio_codec=config.videos.audio_codec,
        )

    logger.info(
        f"Processed video {video_path.name} to {dest_path.resolve()} with size {new_width}x{new_height}"
    )

    return dest_path
