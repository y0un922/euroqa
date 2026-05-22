#!/usr/bin/env bash
set -euo pipefail

TASK_START_REF="${TASK_START_REF:-$(git merge-base HEAD master)}"
violations=$(git diff --name-only "${TASK_START_REF}" HEAD \
  | grep -vE '^experiments/retrieval_eval/' \
  | grep -vE '^\.trellis/' || true)

if [ -n "${violations}" ]; then
  echo "INTRUSION DETECTED. Files outside sandbox were modified:"
  echo "${violations}"
  exit 1
fi

echo "OK: zero intrusion verified."
