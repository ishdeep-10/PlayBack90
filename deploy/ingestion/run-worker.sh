#!/bin/sh
set -eu

repo_dir="${PLAYBACK90_REPO_DIR:-/opt/playback90}"
python_bin="${PLAYBACK90_PYTHON:-${repo_dir}/.venv-ingestion/bin/python}"
league_seasons="${PLAYBACK90_LEAGUE_SEASONS:-mls:2026}"
batch_limit="${PLAYBACK90_BATCH_LIMIT:-8}"

set -- \
  "${repo_dir}/Data/worker_coordinator.py" \
  --run-loop \
  --execute-due \
  --batch-limit "${batch_limit}"

old_ifs="${IFS}"
IFS=','
for target in ${league_seasons}; do
  if [ -n "${target}" ]; then
    set -- "$@" --league-season "${target}"
  fi
done
IFS="${old_ifs}"

exec "${python_bin}" "$@"
