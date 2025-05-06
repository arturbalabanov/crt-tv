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
        timestamp_text_clip = None

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

            timestamp_text_clip = mp.TextClip(
                font=config.timestamp.font_names[0],
                txt=timestamp_text,
                fontsize=config.timestamp.video_font_size,
                color=config.timestamp.fg_color,
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

        if timestamp_text_clip is not None:
            timestamp_text_width, timestamp_text_height = timestamp_text_clip.size
            bg_rect_width = (
                config.videos.timestamp.padding_left
                + timestamp_text_width
                + config.videos.timestamp.padding_right
            )
            bg_rect_height = (
                config.videos.timestamp.padding_top
                + timestamp_text_height
                + config.videos.timestamp.padding_bottom
            )

            bg_rect_clip = mp.ColorClip(
                color=config.timestamp.bg_color_rgb,
                size=(bg_rect_width, bg_rect_height),
            )

            match config.videos.timestamp.position:
                case "top left":
                    timestamp_x = 0
                    timestamp_y = 0
                case "top right":
                    timestamp_x = new_width - bg_rect_width
                    timestamp_y = 0
                case "bottom left":
                    timestamp_x = 0
                    timestamp_y = new_height - bg_rect_height
                case "bottom right":
                    timestamp_x = new_width - bg_rect_width
                    timestamp_y = new_height - bg_rect_height
                case _:
                    raise RuntimeError("invalid branch")

            bg_rect_x = (
                timestamp_x
                + config.videos.timestamp.margin_left
                - config.videos.timestamp.margin_right
            )
            bg_rect_y = (
                timestamp_y
                + config.videos.timestamp.margin_top
                - config.videos.timestamp.margin_bottom
            )
            timestamp_text_x = bg_rect_x + config.videos.timestamp.padding_left
            timestamp_text_y = bg_rect_y + config.videos.timestamp.padding_top

            resized_video = mp.CompositeVideoClip(
                [
                    resized_video,
                    bg_rect_clip.set_duration(video.duration).set_pos(
                        (bg_rect_x, bg_rect_y)
                    ),
                    timestamp_text_clip.set_duration(video.duration).set_pos(
                        (timestamp_text_x, timestamp_text_y)
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
