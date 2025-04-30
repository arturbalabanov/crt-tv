import pathlib

from crt_tv.config import Config


def get_output_image_path(image_path: pathlib.Path, config: Config) -> pathlib.Path:
    relative_source_image_path = image_path.relative_to(config.source_files_dir)

    output_image_path = config.output_files_dir / relative_source_image_path
    output_image_path.parent.mkdir(parents=True, exist_ok=True)

    return output_image_path
