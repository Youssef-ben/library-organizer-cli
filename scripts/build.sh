#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

# shellcheck disable=SC1091
source "$SCRIPT_DIR/bump_version.sh"

CLEAN=false
VERSION_BUMP=""

usage() {
  echo "Usage: $0 [--clean] [--version patch|minor|major]" >&2
  echo "  --clean  Run initialize (clean dirs, recreate venv, install deps). Omit to skip and build with the current environment." >&2
  echo "  --version <patch|minor|major>  Bump __version__ and version_info.txt before build." >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --clean)
      CLEAN=true
      shift
      ;;
    --version=*)
      VERSION_BUMP="${1#*=}"
      if [[ ! "$VERSION_BUMP" =~ ^(patch|minor|major)$ ]]; then
        echo "error: --version must be patch, minor, or major" >&2
        exit 1
      fi
      shift
      ;;
    --version)
      if [[ ! "${2:-}" =~ ^(patch|minor|major)$ ]]; then
        echo "error: --version requires patch, minor, or major" >&2
        usage
        exit 1
      fi
      VERSION_BUMP="$2"
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

if [[ -n "$VERSION_BUMP" ]]; then
  bump_version "$VERSION_BUMP"
  echo
fi

if [[ "$CLEAN" == "true" ]]; then
  source ./scripts/initialize.sh
  echo
fi

echo "================================"
echo "Building the application..."
echo "--------------------------------"
pyinstaller library-organizer-cli.spec

echo "--------------------------------"
echo "Application built successfully."
