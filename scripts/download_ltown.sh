#!/usr/bin/env bash
# Download the official BattLeDIM L-Town nominal EPANET model (L-TOWN.inp)
# from Zenodo record 4017659. Does NOT download L-TOWN_Real.inp.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${ROOT}/data"
OUT_FILE="${OUT_DIR}/L-TOWN.inp"
# Official nominal model file on Zenodo (BattLeDIM dataset v1).
# Use the file URL without ?download=1 — that query form can return HTTP 403.
URL="https://zenodo.org/records/4017659/files/L-TOWN.inp"
EXPECTED_MD5="bfbb16b8b463e0576200ba6ad360f68e"

mkdir -p "${OUT_DIR}"

if [[ -f "${OUT_FILE}" ]]; then
  if command -v md5 >/dev/null 2>&1; then
    CURRENT="$(md5 -q "${OUT_FILE}")"
  elif command -v md5sum >/dev/null 2>&1; then
    CURRENT="$(md5sum "${OUT_FILE}" | awk '{print $1}')"
  else
    CURRENT=""
  fi
  if [[ -n "${CURRENT}" && "${CURRENT}" == "${EXPECTED_MD5}" ]]; then
    echo "L-TOWN.inp already present and checksum matches: ${OUT_FILE}"
    exit 0
  fi
fi

echo "Downloading official L-TOWN.inp (nominal model) from Zenodo…"
echo "  ${URL}"
TMP="${OUT_FILE}.partial"
curl -fL --retry 3 --retry-delay 2 \
  -A "Ripple/0.1 (BattLeDIM research; +https://zenodo.org/records/4017659)" \
  -H "Accept: application/octet-stream" \
  -o "${TMP}" "${URL}"

if command -v md5 >/dev/null 2>&1; then
  GOT="$(md5 -q "${TMP}")"
elif command -v md5sum >/dev/null 2>&1; then
  GOT="$(md5sum "${TMP}" | awk '{print $1}')"
else
  echo "Warning: md5/md5sum not found; skipping checksum verification."
  GOT=""
fi

if [[ -n "${GOT}" && "${GOT}" != "${EXPECTED_MD5}" ]]; then
  rm -f "${TMP}"
  echo "ERROR: checksum mismatch (got ${GOT}, expected ${EXPECTED_MD5})"
  exit 1
fi

mv "${TMP}" "${OUT_FILE}"
echo "Saved ${OUT_FILE}"
if [[ -n "${GOT}" ]]; then
  echo "MD5 OK: ${GOT}"
fi
