#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this setup script as root." >&2
  exit 1
fi

repo_dir="${PLAYBACK90_REPO_DIR:-/opt/playback90}"
worker_user="playback90"
geckodriver_version="0.37.1"

if [ ! -f "${repo_dir}/deploy/ingestion/requirements.txt" ]; then
  echo "Repository not found at ${repo_dir}. Copy or clone it there first." >&2
  exit 1
fi

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  ca-certificates \
  curl \
  firefox-esr \
  git \
  python3 \
  python3-pip \
  python3-venv \
  tar

if ! id "${worker_user}" >/dev/null 2>&1; then
  useradd --system --create-home --home-dir /var/lib/playback90 --shell /usr/sbin/nologin "${worker_user}"
fi

install -d -m 0750 -o "${worker_user}" -g "${worker_user}" /var/lib/playback90
install -d -m 0750 -o "${worker_user}" -g "${worker_user}" /var/lib/playback90/schedule-cache
install -d -m 0750 -o "${worker_user}" -g "${worker_user}" /var/lib/playback90/tmp
install -d -m 0750 -o root -g "${worker_user}" /etc/playback90

architecture="$(dpkg --print-architecture)"
case "${architecture}" in
  amd64) gecko_archive="linux64" ;;
  arm64) gecko_archive="linux-aarch64" ;;
  *) echo "Unsupported architecture: ${architecture}" >&2; exit 1 ;;
esac

gecko_tmp="$(mktemp -d)"
trap 'rm -rf "${gecko_tmp}"' EXIT
curl --fail --location --silent --show-error \
  "https://github.com/mozilla/geckodriver/releases/download/v${geckodriver_version}/geckodriver-v${geckodriver_version}-${gecko_archive}.tar.gz" \
  --output "${gecko_tmp}/geckodriver.tar.gz"
tar -xzf "${gecko_tmp}/geckodriver.tar.gz" -C "${gecko_tmp}"
install -m 0755 "${gecko_tmp}/geckodriver" /usr/local/bin/geckodriver

python3 -m venv "${repo_dir}/.venv-ingestion"
"${repo_dir}/.venv-ingestion/bin/pip" install --no-cache-dir --upgrade pip
"${repo_dir}/.venv-ingestion/bin/pip" install --no-cache-dir -r "${repo_dir}/deploy/ingestion/requirements.txt"

chown -R "${worker_user}:${worker_user}" "${repo_dir}/.venv-ingestion"
chmod 0755 "${repo_dir}/deploy/ingestion/run-worker.sh"

if [ ! -f /etc/playback90/ingestion.env ]; then
  install -m 0600 -o root -g "${worker_user}" \
    "${repo_dir}/deploy/ingestion/playback90-ingestion.env.example" \
    /etc/playback90/ingestion.env
fi
if grep -q '^TMPDIR=/var/tmp/playback90$' /etc/playback90/ingestion.env; then
  sed -i 's|^TMPDIR=/var/tmp/playback90$|TMPDIR=/var/lib/playback90/tmp|' \
    /etc/playback90/ingestion.env
fi

install -m 0644 "${repo_dir}/deploy/ingestion/playback90-ingestion.service" \
  /etc/systemd/system/playback90-ingestion.service

if ! swapon --show=NAME --noheadings | grep -q .; then
  fallocate -l 2G /swapfile
  chmod 0600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  if ! grep -q '^/swapfile ' /etc/fstab; then
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
  fi
fi

systemctl daemon-reload

echo "Setup complete. Edit /etc/playback90/ingestion.env before enabling the service."
