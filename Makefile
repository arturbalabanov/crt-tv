.DEFAULT_GOAL := help

ANSIBLE_GROUP = crt
ANSIBLE_INVENTORY = ansible/inventory.yaml
ANSIBLE_DEPLOY_PLAYBOOK = ansible/playbook-deploy.yaml

SSH_HOST = crt
SYSTEMD_SERVICE_NAME = crt_tv_fs_observer.service
BACKUP_DIR = $(shell dirname ~/backup/crt-tv)/crt-tv

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

.PHONY: ansible-ping
ansible-ping:  ## Ping the raspberry pi to make sure it's reachable and we can deploy
	uv run ansible $(ANSIBLE_GROUP) -m ping -i $(ANSIBLE_INVENTORY)
	
.PHONY: deploy
deploy: clean  ## Deploy the project to the remote host
	uv run ansible-playbook -i $(ANSIBLE_INVENTORY) $(ANSIBLE_DEPLOY_PLAYBOOK)
	
ansible_role_names = $(shell find ansible/roles -type d -maxdepth 1 -mindepth 1  -execdir echo '{}' ';')
$(ansible_role_names): clean   ## Deploy a specific role to the remote host
	uv run ansible all -i ansible/inventory.yaml --module-name include_role --args name=ansible/roles/$@

.PHONY: service-logs
service-logs:  ## Show the logs of the systemd service
	TERM=xterm ssh -t "$(SSH_HOST)" "journalctl _SYSTEMD_INVOCATION_ID=\$$(systemctl show -p InvocationID --value $(SYSTEMD_SERVICE_NAME)) -f"
	
.PHONY: service-status
service-status:  ## Show the logs of the systemd service
	TERM=xterm ssh -t "$(SSH_HOST)" "systemctl status $(SYSTEMD_SERVICE_NAME)"

.PHONY: backup
backup:  ## Backup the Raspberry Pi SD card
	$(eval SD_CARD_DEVICE := $(shell ssh "$(SSH_HOST)" "lsblk -p -n -o PKNAME \$$(findmnt -n -o SOURCE /)"))
	$(eval BACKUP_FILE := $(BACKUP_DIR)/$(shell date +%Y-%m-%dT%H-%M-%S).img.gz)
	
	@echo "Backing up SD card device $(SD_CARD_DEVICE) into local file $(BACKUP_FILE)"
	
	mkdir -p $(BACKUP_DIR)
	ssh "$(SSH_HOST)" "sudo dd if=$(SD_CARD_DEVICE) bs=1M | gzip -" | dd of=$(BACKUP_FILE) status=progress

.PHONY: install
install:  ## Install the CLI tool locally
	uv tool install . --editable --reinstall 

.PHONY: lint
lint:  ## Run the linters and the type checker
	uv run ruff format --check --diff .
	uv run ruff check .
	uv run mypy .
	uv run yamllint --strict .
	uv run ansible-lint

.PHONY: format
format:  ## Run all the formatters
	uv run ruff check . --fix --fix-only --show-fixes
	uv run ruff format .
	uv run ansible-lint --write
