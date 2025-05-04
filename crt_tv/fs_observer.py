import pathlib
import shutil
import time

from loguru import logger
from watchdog.events import (
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileMovedEvent,
    PatternMatchingEventHandler,
)
from watchdog.observers import Observer

from crt_tv.config import Config
from crt_tv.images import process_single_image
from crt_tv.timestamp import get_timestamp_font
from crt_tv.utils import get_output_image_path

# FIXME: Created files are not used to the correct dest path (missing PHOTO/)
# TODO: Add a handler for video files (not processing them for now, simply copying them)


class SourceFileEventHanlder(PatternMatchingEventHandler):
    def __init__(self, config: Config) -> None:
        super().__init__(
            patterns=["*.jpg"],
            ignore_directories=True,
            case_sensitive=False,
        )
        self.config = config

    def _try_process_file(self, file_path: pathlib.Path) -> None:
        if file_path.name.startswith("."):
            logger.debug(f"Skipping hidden file {file_path}")
            return

        try:
            dest_path = process_single_image(file_path, self.config, get_timestamp_font(self.config))
        except Exception:
            logger.exception(f"Error processing file {file_path}")
        else:
            logger.debug(f"Successfully processed file {file_path} -> {dest_path}")

    def _try_delete_processed_file(self, file_path: pathlib.Path) -> None:
        processed_file_path = get_output_image_path(file_path, self.config)

        logger.debug(f"Deleting processed file {processed_file_path}")

        try:
            processed_file_path.unlink()
        except FileNotFoundError:
            logger.warning(f"File {processed_file_path} not found, skipping deletion")
        except Exception:
            logger.exception(f"Error deleting file {processed_file_path}")
        else:
            logger.debug(f"Successfully deleted file {processed_file_path}")

    def on_created(self, event: FileCreatedEvent) -> None:
        file_path = pathlib.Path(event.src_path)
        logger.debug(f"Detected file created: {file_path}")

        self._try_process_file(file_path)

    def on_modified(self, event: FileModifiedEvent) -> None:
        # TODO: Check that the file was actually different (otherwise simply opening them remotely triggers this)
        file_path = pathlib.Path(event.src_path)
        logger.debug(f"Detected file modified: {file_path}")
        self._try_process_file(file_path)

    def on_moved(self, event: FileMovedEvent) -> None:
        # TODO: If moved outside of the source directory, delete the processed file

        old_file_path = pathlib.Path(event.src_path)
        new_file_path = pathlib.Path(event.dest_path)

        logger.debug(f"Detected file moved: {old_file_path} -> {new_file_path}")

        old_processed_file_path = get_output_image_path(old_file_path, self.config)
        new_processed_file_path = get_output_image_path(new_file_path, self.config)

        try:
            logger.debug(f"Moving processed file {old_processed_file_path} -> {new_processed_file_path}")
            shutil.move(old_processed_file_path, new_processed_file_path)
        except Exception:
            logger.exception(f"Error moving file {old_processed_file_path} -> {new_processed_file_path}")
        else:
            logger.debug(f"Successfully moved file {old_processed_file_path} -> {new_processed_file_path}")

    def on_deleted(self, event: FileDeletedEvent) -> None:
        old_file_path = pathlib.Path(event.src_path)
        logger.debug(f"Detected file deleted: {old_file_path}")
        self._try_delete_processed_file(old_file_path)


def observe_and_action_fs_events(
    config: Config,
    *,
    recursive: bool = True,
    sleep_time: float = 0.1,
) -> None:
    logger.info(f"Starting to observe file system events for source files in {config.source_files_dir}")

    event_handler = SourceFileEventHanlder(config)
    observer = Observer()

    observer.schedule(event_handler, str(config.source_files_dir.resolve()), recursive=recursive)
    observer.start()

    try:
        while True:
            time.sleep(sleep_time)
    finally:
        logger.info("Stopping file system observer")
        observer.stop()
        observer.join()
