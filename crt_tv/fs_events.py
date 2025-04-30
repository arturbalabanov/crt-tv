import pathlib
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

from crt_tv.cli import process_single_file


class SourceFileEventHanlder(PatternMatchingEventHandler):
    def __init__(self) -> None:
        super().__init__(
            patterns=["*.jpg"],
            ignore_directories=True,
            case_sensitive=False,
        )

    def _try_process_file(self, file_path: pathlib.Path) -> None:
        try:
            dest_path = process_single_file(file_path)
        except Exception:
            logger.exception(f"Error processing file {file_path}")
        else:
            logger.debug(f"Successfully processed file {file_path} -> {dest_path}")

    def _get_processed_file_path(self, file_path: pathlib.Path) -> pathlib.Path:
        logger.debug(f"Getting processed file path for {file_path}")

        raise NotImplementedError()  # TODO: Implement me

    def _try_delete_processed_file(self, file_path: pathlib.Path) -> None:
        processed_file_path = self._get_processed_file_path(file_path)

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
        file_path = pathlib.Path(event.src_path)
        logger.debug(f"Detected file modified: {file_path}")
        self._try_process_file(file_path)

    def on_moved(self, event: FileMovedEvent) -> None:
        old_file_path = pathlib.Path(event.src_path)
        new_file_path = pathlib.Path(event.dest_path)

        logger.debug(f"Detected file moved: {old_file_path} -> {new_file_path}")

        # TODO: Maybe just move the processed file?
        self._try_process_file(new_file_path)
        self._try_delete_processed_file(old_file_path)

    def on_deleted(self, event: FileDeletedEvent) -> None:
        old_file_path = pathlib.Path(event.src_path)
        logger.debug(f"Detected file deleted: {old_file_path}")
        self._try_delete_processed_file(old_file_path)


def observe_and_action_fs_events(
    path: pathlib.Path,
    *,
    recursive: bool = True,
    sleep_time: float = 0.1,
) -> None:
    if not path.is_dir():
        raise OSError(f"Path {path} is not a directory")

    logger.info("Starting to observe file system events")

    event_handler = SourceFileEventHanlder()
    observer = Observer()

    observer.schedule(event_handler, str(path.resolve()), recursive=recursive)
    observer.start()

    try:
        while True:
            time.sleep(sleep_time)
    finally:
        observer.stop()
        observer.join()
