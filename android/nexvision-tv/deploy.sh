#!/usr/bin/env bash
# deploy.sh — Build, sideload, and launch NexVision TV on a Mi TV Stick 4K via ADB/Wi-Fi
# Usage:
#   ./deploy.sh               # install debug APK (default)
#   ./deploy.sh release       # build + install release APK
#   BUILD=0 ./deploy.sh       # skip Gradle build, install whatever APK already exists
set -euo pipefail

# ── Configuration ──────────────────────────────────────────────────────────────

DEVICE_IP=192.168.1.100        # ← replace with your Mi TV Stick IP
ADB_PORT=5555                       # Android ADB-over-Wi-Fi default port
PACKAGE="com.nexvision.tv"
ACTIVITY=".MainActivity"            # resolved against PACKAGE by am start
ADB_CONNECT_RETRIES=5               # attempts before giving up
ADB_CONNECT_DELAY=3                 # seconds between attempts

# Build variant: "debug" | "release"
VARIANT="${1:-debug}"

# Set to 0 to skip the Gradle build step (just deploy whatever APK exists)
BUILD="${BUILD:-1}"

# Derived APK path (matches Gradle default output location)
APK_PATH="app/build/outputs/apk/${VARIANT}/app-${VARIANT}.apk"

# ── Colour helpers ─────────────────────────────────────────────────────────────

if [[ -t 1 ]]; then          # only colour when stdout is a terminal
    RED='\033[0;31m'  GRN='\033[0;32m'  YLW='\033[0;33m'
    BLU='\033[0;34m'  DIM='\033[2m'     RST='\033[0m'
else
    RED='' GRN='' YLW='' BLU='' DIM='' RST=''
fi

step()  { echo -e "${BLU}▶  $*${RST}"; }
ok()    { echo -e "${GRN}✓  $*${RST}"; }
warn()  { echo -e "${YLW}⚠  $*${RST}"; }
die()   { echo -e "${RED}✗  $*${RST}" >&2; exit 1; }

# ── Sanity checks ──────────────────────────────────────────────────────────────

command -v adb  >/dev/null 2>&1 || die "adb not found — install Android platform-tools and add to PATH."
command -v grep >/dev/null 2>&1 || die "grep not found."


# ── Optional Gradle build ──────────────────────────────────────────────────────

if [[ "$BUILD" == "1" ]]; then
    step "Building ${VARIANT} APK…"

    GRADLE_CMD="./gradlew"
    [[ ! -x "$GRADLE_CMD" ]] && die "gradlew not found. Run this script from the project root."

    # Capitalise first letter for the Gradle task name (debug → Debug)
    TASK="assemble${VARIANT^}"
    "$GRADLE_CMD" "$TASK" --quiet || die "Gradle build failed."
    ok "Build complete → ${APK_PATH}"
else
    warn "Skipping build (BUILD=0)."
fi

[[ -f "$APK_PATH" ]] || die "APK not found at '${APK_PATH}'. Build the project first."

# ── ADB connection ─────────────────────────────────────────────────────────────

step "Connecting to ${DEVICE_IP}:${ADB_PORT}…"

# Disconnect any stale session for this device first (ignore failure)
adb disconnect "${DEVICE_IP}:${ADB_PORT}" >/dev/null 2>&1 || true

connected=0
for attempt in $(seq 1 "$ADB_CONNECT_RETRIES"); do
    output=$(adb connect "${DEVICE_IP}:${ADB_PORT}" 2>&1)
    if echo "$output" | grep -qiE "connected to|already connected"; then
        connected=1
        break
    fi
    warn "Attempt ${attempt}/${ADB_CONNECT_RETRIES} failed (${output}). Retrying in ${ADB_CONNECT_DELAY}s…"
    sleep "$ADB_CONNECT_DELAY"
done

[[ "$connected" -eq 1 ]] || die "Could not connect to ${DEVICE_IP}:${ADB_PORT}.\n   Check: device on same network, Developer Options on, Network Debugging on."

TARGET="${DEVICE_IP}:${ADB_PORT}"

# Confirm the device is actually responsive
adb -s "$TARGET" get-state >/dev/null 2>&1 || \
    die "Device found but unresponsive. Check USB Debugging authorisation on the TV."
ok "Connected to ${TARGET}."

# ── Uninstall existing version ─────────────────────────────────────────────────

step "Uninstalling existing ${PACKAGE} (if present)…"

if adb -s "$TARGET" shell pm list packages 2>/dev/null | grep -qF "package:${PACKAGE}"; then
    adb -s "$TARGET" uninstall "$PACKAGE" >/dev/null
    ok "Uninstalled."
else
    ok "Not installed — nothing to remove."
fi

# ── Install new APK ────────────────────────────────────────────────────────────

step "Installing ${APK_PATH}…"
INSTALL_OUT=$(adb -s "$TARGET" install -r -t "$APK_PATH" 2>&1)

# adb install returns exit 0 even on some failures; check stdout explicitly
if echo "$INSTALL_OUT" | grep -q "^Success"; then
    ok "APK installed."
else
    die "Installation failed:\n${INSTALL_OUT}"
fi

# ── Launch ─────────────────────────────────────────────────────────────────────

step "Launching ${PACKAGE}/${ACTIVITY}…"

LAUNCH_OUT=$(adb -s "$TARGET" shell am start \
    -n "${PACKAGE}/${ACTIVITY}" \
    -a android.intent.action.MAIN \
    -c android.intent.category.LEANBACK_LAUNCHER \
    2>&1)

if echo "$LAUNCH_OUT" | grep -qiE "error|exception|not found"; then
    die "Launch failed:\n${LAUNCH_OUT}"
fi

ok "Launched."

# ── Done ───────────────────────────────────────────────────────────────────────

echo
echo -e "${GRN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RST}"
echo -e "${GRN}  NexVision TV deployed to ${TARGET}${RST}"
echo -e "${GRN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RST}"
echo
echo -e "  ${DIM}Watch logcat:   adb -s ${TARGET} logcat -s 'chromium' 'WebView'${RST}"
echo -e "  ${DIM}Disconnect:     adb disconnect ${TARGET}${RST}"
echo
