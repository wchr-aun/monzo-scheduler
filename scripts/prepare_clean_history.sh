#!/usr/bin/env bash
# Prepare a reviewable sanitized mirror. Never changes this checkout or any remote.
set -euo pipefail
repo_root="$(git rev-parse --show-toplevel)"
if [[ $# != 1 || -e "$1" ]]; then
  printf '%s\n' 'Usage: prepare_clean_history.sh <new private output directory>' >&2
  exit 1
fi
umask 077
mkdir -p "$1"
output_dir="$(cd "$1" && pwd)"
git clone --mirror --no-hardlinks "$repo_root" "$output_dir/repository.git"
(
  cd "$output_dir/repository.git"
  uvx --from git-filter-repo==2.47.0 git-filter-repo --force --invert-paths \
    --path-glob '*.db' --path-glob '*.db-*' \
    --path-glob '*.sqlite' --path-glob '*.sqlite-*' \
    --path-glob '*.sqlite3' --path-glob '*.sqlite3-*'
  git fsck --full
  git bundle create "$output_dir/clean-history.bundle" --all
  cp filter-repo/commit-map "$output_dir/commit-map.txt"
)
printf 'Sanitized review artifact: %s\n' "$output_dir/clean-history.bundle"
printf '%s\n' 'No remote was changed. Review all refs and coordinate remote replacement separately.'
