import pathlib

from crt_tv.config import Config


def get_output_path(source_path: pathlib.Path, config: Config) -> pathlib.Path:
    dest_suffix = ".mp4" if source_path.suffix.lower() == ".avi" else source_path.suffix

    relative_source_path = source_path.relative_to(config.source_files_dir)

    output_path = config.output_files_dir / relative_source_path.with_suffix(dest_suffix)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    return output_path
