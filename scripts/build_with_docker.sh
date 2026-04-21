#!/bin/bash
# Build a Linux ELF in dist/ using PyInstaller inside a Linux container (no local Python venv required).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

IMAGE="${IMAGE:-python:3.12-bookworm}"

usage() {
  echo "Usage: $0 [--image <docker-image>]" >&2
  echo "  Builds dist/library-organizer-cli via PyInstaller inside Docker." >&2
  echo "  Requires Docker. Run from any OS with Docker Desktop / Engine." >&2
  echo "  Override image: IMAGE=python:3.12-slim $0  or  $0 --image python:3.12-slim" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --image)
      if [[ -z "${2:-}" ]]; then
        echo "error: --image requires a value" >&2
        exit 1
      fi
      IMAGE="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "error: unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if ! command -v docker >/dev/null 2>&1; then
  echo "error: docker not found on PATH" >&2
  exit 1
fi

echo "================================"
echo "Docker image: $IMAGE"
echo "Project root:  $REPO_ROOT"
echo "--------------------------------"

# Git Bash on Windows rewrites paths like /repo to under Program Files/Git; disable for Docker args.
if [[ -n "${MSYSTEM:-}" ]] || [[ "$(uname -s 2>/dev/null)" == MINGW* ]]; then
  export MSYS_NO_PATHCONV=1
fi

docker run --rm -i \
  -v "$REPO_ROOT:/repo" \
  -w /repo \
  "$IMAGE" \
  bash -lc "set -euo pipefail
pip install --upgrade pip
pip install -e '.[dev]'
pyinstaller library-organizer-cli.spec"

echo "--------------------------------"
echo "Done. Linux binary: $REPO_ROOT/dist/library-organizer-cli"