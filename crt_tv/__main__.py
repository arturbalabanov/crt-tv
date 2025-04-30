from crt_tv import cli

# TODO: Add automatic image rotation
#       Exif data is not present for these files but a simple check could be
#       to rotate clockwise until the timestamp is found
#       Actually, this doesn't work as the timestamp is alwaus horizonal...

# TODO: Clean the output dir before the run in case we removed files from source dir
#       Actually, this script takes long time to run on the Raspberry Pi, especially
#       with a big library, so instead it should have a flag to re-generate all pictures
#       (in which case, remove the output dir) and instead generate only for new pictures
#       and remove previously processed ones which are not found in the source dir anymore


# TODO: Only search the bottom part of the image for the timestamp

# TODO: Add support for videos


cli.app()
