.DEFAULT_GOAL := help

SSH_HOST = crt
SYSTEMD_SERVICE_NAME = crt_tv_fs_observer.service

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
	ssh "$(SSH_HOST)" "rm -rf /opt/crt-tv"
	ssh "$(SSH_HOST)" "git clone https://github.com/arturbalabanov/crt-tv/ /opt/crt-tv"
	ssh "$(SSH_HOST)" "cd /opt/crt-tv && ./install.sh"

.PHONY: service-logs
service-logs:  ## Show the logs of the systemd service
	TERM=xterm ssh -t "$(SSH_HOST)" "journalctl _SYSTEMD_INVOCATION_ID=\$$(systemctl show -p InvocationID --value $(SYSTEMD_SERVICE_NAME)) -f"
	
.PHONY: service-status
service-status:  ## Show the logs of the systemd service
	TERM=xterm ssh -t "$(SSH_HOST)" "systemctl status $(SYSTEMD_SERVICE_NAME)"

.PHONY: install
install:  ## Install the CLI tool locally
	uv tool install . --editable --reinstall 


.PHONY: lint
lint:  ## Run the linters and the type checker
	uv run ruff format --check --diff .
	uv run ruff check .
	uv run mypy .

.PHONY: format
format:  ## Run all the formatters
	uv run ruff check . --fix --fix-only --show-fixes
	uv run ruff format .
