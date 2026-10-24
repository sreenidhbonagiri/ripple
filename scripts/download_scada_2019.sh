#!/usr/bin/env bash
# Download official 2019 SCADA pressure/flow/level CSVs (+ config) from Zenodo 4017659.
# Does NOT download leak ground-truth files.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${ROOT}/data/raw"
BASE="https://zenodo.org/records/4017659/files"
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

mkdir -p "${OUT_DIR}"

download() {
  local name="$1"
  local md5="$2"
  local dest="${OUT_DIR}/${name}"
  if [[ -f "${dest}" ]]; then
    local current=""
    if command -v md5 >/dev/null 2>&1; then
      current="$(md5 -q "${dest}")"
    elif command -v md5sum >/dev/null 2>&1; then
      current="$(md5sum "${dest}" | awk '{print $1}')"
    fi
    if [[ -n "${current}" && "${current}" == "${md5}" ]]; then
      echo "OK ${name} (checksum match)"
      return 0
    fi
  fi
  echo "Downloading ${name}…"
  local tmp="${dest}.partial"
  if ! curl -fL --retry 3 --retry-delay 2 -A "${UA}" -o "${tmp}" "${BASE}/${name}"; then
    echo "ERROR: Zenodo download failed for ${name} (HTTP/network). Place the official file at ${dest}."
    rm -f "${tmp}"
    return 1
  fi
  local got=""
  if command -v md5 >/dev/null 2>&1; then
    got="$(md5 -q "${tmp}")"
  elif command -v md5sum >/dev/null 2>&1; then
    got="$(md5sum "${tmp}" | awk '{print $1}')"
  fi
  if [[ -n "${got}" && "${got}" != "${md5}" ]]; then
    rm -f "${tmp}"
    echo "ERROR: checksum mismatch for ${name}"
    return 1
  fi
  mv "${tmp}" "${dest}"
  echo "Saved ${dest}"
}

# Official Zenodo MD5s (record 4017659) — no leak files
download "2019_SCADA_Pressures.csv" "5ea1e46d3f2f0a89a3f98d6fd39a851d"
download "2019_SCADA_Flows.csv" "28fc99fdcbf80fcd26079e7fe602d6dc"
download "2019_SCADA_Levels.csv" "e5a8050bd38729e4b7648b9d52abd5b1"
download "dataset_configuration.yaml" "48486401f5b4d0447023f5ce5d242c52"

echo "Done. Leak ground-truth files were not downloaded."
