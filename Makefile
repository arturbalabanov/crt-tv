SSH_HOST = crt
REMOTE_PATH = /media/usb1/retrosnap
PYTHON_SCRIPTS = $(wildcard *.py)
ASSETS_DIR = assets

deploy:
	scp $(PYTHON_SCRIPTS) "$(SSH_HOST):$(REMOTE_PATH)"
	scp -r $(ASSETS_DIR) "$(SSH_HOST):$(REMOTE_PATH)"
