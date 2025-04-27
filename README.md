A collection of scripts I'm running on a Raspberry Pi connected to a CRT TV

For my own use only, sharing them in case someone else may find them useful
for their own projects.

`resize_images.py`
------------------

Resizes images captured by my tiny [RetroSnap](https://theretrosnap.com/products/retro-snap) camera.
Unfortunately, the camera captures them in close to 16:9 ratio with no option to do it in 4:3 instead
which is what most CRT TVs use. It's extra annoying because the camera's own display is 4:3 but what 
can you do... This script resizes the images by either cropping them or stretching them to 4:3
(or any other desired aspect ratio).

Additionally, the camera post processes the images by stamping them with the current date and time
which adds to the retro vibe and is great to be there when viewing them. However, when cropping the photos
the most useful part of the timestamp -- the date, is no longer in frame, so this script also uses image
recognision to try to extract it from the original image and re-apply it in the cropped photos

Example usage:

```sh
uv run resize_images.py --input-dir ~/retrosnap-photos --output-dir ~/cropped-photos --resize-method crop --timestamp-position "bottom left" 
```

Use  `resize_images.py --help` for all options as well as the contents of the script itself
