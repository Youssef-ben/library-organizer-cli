#!/bin/bash
# Bump MAJOR.MINOR.PATCH in src/library_organizer_cli/__init__.py and matching tuples /
# FileVersion / ProductVersion in version_info.txt (regex parse + replace).
# Usage: source from build.sh, or run: bash scripts/bump_version.sh <patch|minor|major>

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VERSION_FILE="${REPO_ROOT}/src/library_organizer_cli/__init__.py"
VERSION_INFO_FILE="${REPO_ROOT}/version_info.txt"

# Args: new major minor patch (after bump). Updates filevers/prodvers and FileVersion/ProductVersion.
bump_version_info_txt() {
  local ma="$1" mi="$2" pa="$3"
  local vf="$VERSION_INFO_FILE"
  local win_ver tmp line
  win_ver="${ma}.${mi}.${pa}.0"

  if [[ ! -f "$vf" ]]; then
    echo "warning: $vf not found; skipping Windows version_info.txt update" >&2
    return 0
  fi

  tmp=$(mktemp 2>/dev/null || echo "${vf}.tmp.$$")
  local re_filevers='^([[:space:]]*filevers=)\(([^)]+)\)(.*)$'
  local re_prodvers='^([[:space:]]*prodvers=)\(([^)]+)\)(.*)$'
  local re_fv='^([[:space:]]*StringStruct\(u"FileVersion", u")([^"]+)(".*)$'
  local re_pv='^([[:space:]]*StringStruct\(u"ProductVersion", u")([^"]+)(".*)$'

  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ $line =~ $re_filevers ]]; then
      printf '%s(%s, %s, %s, 0)%s\n' "${BASH_REMATCH[1]}" "$ma" "$mi" "$pa" "${BASH_REMATCH[3]}"
    elif [[ $line =~ $re_prodvers ]]; then
      printf '%s(%s, %s, %s, 0)%s\n' "${BASH_REMATCH[1]}" "$ma" "$mi" "$pa" "${BASH_REMATCH[3]}"
    elif [[ $line =~ $re_fv ]]; then
      printf '%s%s%s\n' "${BASH_REMATCH[1]}" "$win_ver" "${BASH_REMATCH[3]}"
    elif [[ $line =~ $re_pv ]]; then
      printf '%s%s%s\n' "${BASH_REMATCH[1]}" "$win_ver" "${BASH_REMATCH[3]}"
    else
      printf '%s\n' "$line"
    fi
  done <"$vf" >"$tmp"
  mv "$tmp" "$vf"
  echo "Updated: $vf (filevers/prodvers + FileVersion/ProductVersion -> $win_ver)"
}

bump_version() {
  local bump="$1"
  local f="$VERSION_FILE"
  local line ma mi pa old_ver new_ver tmp re_parse re_line
  
  echo "Upgrading the ($bump) version..."
  echo "--------------------------------"

  line=$(grep -E '^__version__' "$f" || true)
  if [[ -z "$line" ]]; then
    echo "error: could not find __version__ in $f" >&2
    return 1
  fi

  re_parse='^__version__[[:space:]]*=[[:space:]]*"([0-9]+)\.([0-9]+)\.([0-9]+)"'
  if [[ ! $line =~ $re_parse ]]; then
    echo "error: could not parse __version__ in $f" >&2
    return 1
  fi
  ma=${BASH_REMATCH[1]}
  mi=${BASH_REMATCH[2]}
  pa=${BASH_REMATCH[3]}
  old_ver="${ma}.${mi}.${pa}"

  case "$bump" in
    patch) pa=$((pa + 1)) ;;
    minor) mi=$((mi + 1)); pa=0 ;;
    major) ma=$((ma + 1)); mi=0; pa=0 ;;
  esac
  new_ver="${ma}.${mi}.${pa}"

  tmp=$(mktemp 2>/dev/null || echo "${f}.tmp.$$")
  re_line='^(__version__[[:space:]]*=[[:space:]]*")[^"]+(")$'
  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ $line =~ $re_line ]]; then
      printf '%s%s%s\n' "${BASH_REMATCH[1]}" "$new_ver" "${BASH_REMATCH[2]}"
    else
      printf '%s\n' "$line"
    fi
  done <"$f" >"$tmp"
  mv "$tmp" "$f"

  bump_version_info_txt "$ma" "$mi" "$pa"

  echo "Version upgraded: [$old_ver] ==> [$new_ver]"
  echo "--------------------------------"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  set -euo pipefail
  if [[ $# -ne 1 ]] || [[ ! $1 =~ ^(patch|minor|major)$ ]]; then
    echo "Usage: $(basename "$0") <patch|minor|major>" >&2
    exit 1
  fi
  bump_version "$1"
fi


