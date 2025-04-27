SSH_HOST = crt
REMOTE_PATH = /media/usb1/retrosnap
PYTHON_SCRIPTS = $(wildcard *.py)

deploy:
	scp $(PYTHON_SCRIPTS) "$(SSH_HOST):$(REMOTE_PATH)"
