#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VERSION="v0.2.0"
SOURCE_ICON="${PROJECT_ROOT}/assets/KOLConnect.png"
GENERATED_ICON="${PROJECT_ROOT}/assets/KOLConnect.icns"
ICONSET_DIR="${SCRIPT_DIR}/KOLConnect.iconset"
WORK_DIR="${SCRIPT_DIR}/.pyinstaller-build-macos"
DIST_DIR="${SCRIPT_DIR}/.pyinstaller-dist-macos"
DMG_STAGE="${SCRIPT_DIR}/.macos-dmg-staging"
SPEC_FILE="${SCRIPT_DIR}/spec/KOLConnect_mac.spec"
APP_PATH="${DIST_DIR}/KOLConnect.app"
RELEASE_DIR="${PROJECT_ROOT}/release"
DMG_PATH="${RELEASE_DIR}/KOLConnect_${VERSION}_mac_arm64.dmg"

cleanup() {
  rm -rf "${ICONSET_DIR}" "${DMG_STAGE}"
}
trap cleanup EXIT

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "macOS build requires Darwin." >&2
  exit 1
fi

ARCH="$(uname -m)"
PYTHON_ARCH="$(python -c 'import platform; print(platform.machine())')"
echo "uname -m: ${ARCH}"
echo "platform.machine(): ${PYTHON_ARCH}"
if [[ "${ARCH}" != "arm64" || "${PYTHON_ARCH}" != "arm64" ]]; then
  echo "macOS arm64 build requires an arm64 OS and Python runtime." >&2
  exit 1
fi

if [[ ! -f "${SOURCE_ICON}" ]]; then
  echo "Application icon source is missing: ${SOURCE_ICON}" >&2
  exit 1
fi
if [[ ! -f "${SPEC_FILE}" ]]; then
  echo "PyInstaller spec is missing: ${SPEC_FILE}" >&2
  exit 1
fi

WIDTH="$(sips -g pixelWidth "${SOURCE_ICON}" 2>/dev/null | awk '/pixelWidth/ {print $2}')"
HEIGHT="$(sips -g pixelHeight "${SOURCE_ICON}" 2>/dev/null | awk '/pixelHeight/ {print $2}')"
if [[ ! "${WIDTH}" =~ ^[0-9]+$ || ! "${HEIGHT}" =~ ^[0-9]+$ ]]; then
  echo "Unable to read source icon dimensions with sips." >&2
  exit 1
fi
if (( WIDTH < 1024 || HEIGHT < 1024 )); then
  echo "Source icon must be at least 1024x1024; found ${WIDTH}x${HEIGHT}." >&2
  exit 1
fi

rm -rf "${ICONSET_DIR}" "${WORK_DIR}" "${DIST_DIR}" "${DMG_STAGE}"
mkdir -p "${ICONSET_DIR}" "${RELEASE_DIR}"

sips -z 16 16 "${SOURCE_ICON}" --out "${ICONSET_DIR}/icon_16x16.png" >/dev/null
sips -z 32 32 "${SOURCE_ICON}" --out "${ICONSET_DIR}/icon_16x16@2x.png" >/dev/null
sips -z 32 32 "${SOURCE_ICON}" --out "${ICONSET_DIR}/icon_32x32.png" >/dev/null
sips -z 64 64 "${SOURCE_ICON}" --out "${ICONSET_DIR}/icon_32x32@2x.png" >/dev/null
sips -z 128 128 "${SOURCE_ICON}" --out "${ICONSET_DIR}/icon_128x128.png" >/dev/null
sips -z 256 256 "${SOURCE_ICON}" --out "${ICONSET_DIR}/icon_128x128@2x.png" >/dev/null
sips -z 256 256 "${SOURCE_ICON}" --out "${ICONSET_DIR}/icon_256x256.png" >/dev/null
sips -z 512 512 "${SOURCE_ICON}" --out "${ICONSET_DIR}/icon_256x256@2x.png" >/dev/null
sips -z 512 512 "${SOURCE_ICON}" --out "${ICONSET_DIR}/icon_512x512.png" >/dev/null
sips -z 1024 1024 "${SOURCE_ICON}" --out "${ICONSET_DIR}/icon_512x512@2x.png" >/dev/null
iconutil -c icns "${ICONSET_DIR}" -o "${GENERATED_ICON}"

python -m PyInstaller --noconfirm --clean \
  --workpath "${WORK_DIR}" \
  --distpath "${DIST_DIR}" \
  "${SPEC_FILE}"

if [[ ! -d "${APP_PATH}" ]]; then
  echo "PyInstaller did not generate ${APP_PATH}." >&2
  exit 1
fi

codesign --force --deep --sign - "${APP_PATH}"
codesign --verify --deep --strict --verbose=2 "${APP_PATH}"

mkdir -p "${DMG_STAGE}"
ditto "${APP_PATH}" "${DMG_STAGE}/KOLConnect.app"
ln -s /Applications "${DMG_STAGE}/Applications"
rm -f "${DMG_PATH}"
hdiutil create \
  -volname "KOLConnect ${VERSION}" \
  -srcfolder "${DMG_STAGE}" \
  -ov \
  -format UDZO \
  "${DMG_PATH}"

if [[ ! -f "${DMG_PATH}" ]]; then
  echo "DMG generation failed: ${DMG_PATH}" >&2
  exit 1
fi

echo "APP path: ${APP_PATH}"
echo "DMG path: ${DMG_PATH}"
echo "CPU architecture: ${ARCH}"
shasum -a 256 "${DMG_PATH}"
