#!/usr/bin/env bash

set -euo pipefail

service_name="crt_tv_fs_observer.service"
service_path="/etc/systemd/system/$service_name"

uv tool install . --reinstall

cp "$service_name" "/etc/systemd/system/$service_name"
chown root:root $service_path
chmod 644 $service_path

systemctl daemon-reload
systemctl enable $service_name
systemctl start $service_name
