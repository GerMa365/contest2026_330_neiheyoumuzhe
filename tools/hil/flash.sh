#!/usr/bin/env bash
#
# SiliconLoop: the only sanctioned way to flash the ESP32-P4 board.
#
# The flash address is hard-coded to 0x2000. Writing to 0x0 overwrites the
# bootloader region and leaves the board unbootable, so the address is
# deliberately not a parameter.
#
# Usage (from anywhere):
#   PORT=/dev/ttyACM0 contest2026_330_neiheyoumuzhe/tools/hil/flash.sh [image]
#
# image defaults to <openvela root>/nuttx/nuttx.bin

set -euo pipefail

FLASH_ADDR="0x2000"
PORT="${PORT:-/dev/ttyACM0}"
BAUD="${BAUD:-921600}"
WAIT_SECS="${WAIT_SECS:-15}"

# tools/hil -> repo -> openvela root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
IMAGE="${1:-${ROOT}/nuttx/nuttx.bin}"

log() { printf '[flash] %s\n' "$*"; }
die() { printf '[flash] ERROR: %s\n' "$*" >&2; exit 1; }

# 1. Image sanity checks
[[ -f "${IMAGE}" ]] || die "image not found: ${IMAGE} (build first)"
[[ -s "${IMAGE}" ]] || die "image is empty: ${IMAGE}"
case "${IMAGE}" in
  *.bin) ;;
  *) die "refusing to flash a non-.bin file: ${IMAGE}" ;;
esac

# 2. Locate esptool
if command -v esptool >/dev/null 2>&1; then
  ESPTOOL=(esptool)
elif command -v esptool.py >/dev/null 2>&1; then
  ESPTOOL=(esptool.py)
elif python3 -c 'import esptool' >/dev/null 2>&1; then
  ESPTOOL=(python3 -m esptool)
else
  die "esptool not found (pip install esptool)"
fi

# 3. Wait for the serial port (USB re-enumerates after every reset)
for ((i = 0; i < WAIT_SECS; i++)); do
  [[ -e "${PORT}" ]] && break
  sleep 1
done
[[ -e "${PORT}" ]] || die "serial port ${PORT} not present after ${WAIT_SECS}s"

# 4. Flash
log "image : ${IMAGE} ($(stat -c %s "${IMAGE}" 2>/dev/null || wc -c < "${IMAGE}") bytes)"
log "port  : ${PORT} @ ${BAUD}"
log "addr  : ${FLASH_ADDR} (fixed)"

"${ESPTOOL[@]}" --chip esp32p4 -p "${PORT}" -b "${BAUD}" \
  write_flash "${FLASH_ADDR}" "${IMAGE}"

log "done; the board resets and USB re-enumerates, wait a few seconds before opening the port"
