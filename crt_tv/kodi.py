import functools
import subprocess

from crt_tv.config import Config


def is_kodi_running() -> bool:
    try:
        output = subprocess.check_output(["pgrep", "-f", "kodi"], text=True)
        if output:
            return True
    except subprocess.CalledProcessError:
        pass

    return False


def require_kodi_running(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if not is_kodi_running():
            raise RuntimeError("Kodi is not running")

        return func(*args, **kwargs)

    return wrapper


@require_kodi_running
def kodi_send(action: str) -> subprocess.CompletedProcess:
    if not is_kodi_running():
        raise RuntimeError("Kodi is not running")

    try:
        return subprocess.run(["kodi-send", "--action", action], check=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to send action to Kodi: {e}") from e


@require_kodi_running
def start_slideshow(config: Config) -> None:
    kodi_send(f"RecursiveSlideShow({config.output_files_dir.resolve()})")


@require_kodi_running
def refresh_slideshow(config: Config) -> None:
    kodi_send("Back")
    start_slideshow(config)


@require_kodi_running
def open_shutdown_menu() -> None:
    kodi_send("ActivateWindow(10111)")
