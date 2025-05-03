.DEFAULT_GOAL := help

SSH_HOST = crt
REMOTE_PROJECT_PATH = /root/.local/share/crt-tv
SYSTEMD_SERVICE_NAME = crt_tv_fs_observer.service
REMOTE_SYSTEMD_SEVERICE_PATH = /etc/systemd/system/$(SYSTEMD_SERVICE_NAME)

.PHONY: help
help:  ## Generates a help README
	@cat $(MAKEFILE_LIST) \
		| grep -E '^[a-zA-Z_-]+:.*?## .*$$' \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'
	
.PHONY: clean
clean:  ## Remove the build artifacts
	rm -rf __pycache__
	rm -rf crt_tv/__pycache__
	
.PHONY: deploy
deploy:  clean ## Deploy the project to the remote host
	ssh "$(SSH_HOST)" "mkdir -p $(REMOTE_PROJECT_PATH)"
	scp pyproject.toml "$(SSH_HOST):$(REMOTE_PROJECT_PATH)"
	scp uv.lock "$(SSH_HOST):$(REMOTE_PROJECT_PATH)"
	scp -r crt_tv "$(SSH_HOST):$(REMOTE_PROJECT_PATH)"
	scp -r assets "$(SSH_HOST):$(REMOTE_PROJECT_PATH)"
	scp "$(SYSTEMD_SERVICE_NAME)" "$(SSH_HOST):$(REMOTE_SYSTEMD_SEVERICE_PATH)"
	ssh "$(SSH_HOST)" "chown root:root $(REMOTE_SYSTEMD_SEVERICE_PATH)"
	ssh "$(SSH_HOST)" "chmod 644 $(REMOTE_SYSTEMD_SEVERICE_PATH)"
	ssh "$(SSH_HOST)" "systemctl daemon-reload"
	ssh "$(SSH_HOST)" "systemctl enable $(SYSTEMD_SERVICE_NAME)"
	ssh "$(SSH_HOST)" "systemctl start $(SYSTEMD_SERVICE_NAME)"

.PHONY: service-logs
service-logs:  ## Show the logs of the systemd service
	TERM=xterm ssh -t "$(SSH_HOST)" "journalctl _SYSTEMD_INVOCATION_ID=\$$(systemctl show -p InvocationID --value $(SYSTEMD_SERVICE_NAME)) -f"
	
.PHONY: service-status
service-status:  ## Show the logs of the systemd service
	TERM=xterm ssh -t "$(SSH_HOST)" "systemctl status $(SYSTEMD_SERVICE_NAME)"

.PHONY: lint
lint:  ## Run the linters and the type checker
	uv run ruff format --check --diff .
	uv run ruff check .
	uv run mypy .

.PHONY: format
format:  ## Run all the formatters
	uv run ruff check . --fix --fix-only --show-fixes
	uv run ruff format .
