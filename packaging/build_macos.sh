#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VERSION="v0.2.0"
SOURCE_ICON="${PROJECT_ROOT}/assets/KOLConnect.png"
GENERATED_ICON="${PROJECT_ROOT}/assets/KOLConnect.icns"
ICONSET_DIR="${SCRIPT_DIR}/KOLConnect.iconset"
TARGET_ARCH="${1:-arm64}"
RELEASE_DIR="${PROJECT_ROOT}/release"

if (( $# > 1 )); then
  echo "Usage: $0 [arm64|x86_64]" >&2
  exit 1
fi

case "${TARGET_ARCH}" in
  arm64)
    WORK_DIR="${SCRIPT_DIR}/.pyinstaller-build-macos"
    DIST_DIR="${SCRIPT_DIR}/.pyinstaller-dist-macos"
    DMG_STAGE="${SCRIPT_DIR}/.macos-dmg-staging"
    SPEC_FILE="${SCRIPT_DIR}/spec/KOLConnect_mac.spec"
    DMG_PATH="${RELEASE_DIR}/KOLConnect_${VERSION}_mac_arm64.dmg"
    ;;
  x86_64)
    WORK_DIR="${PROJECT_ROOT}/build/pyinstaller-macos-intel"
    DIST_DIR="${PROJECT_ROOT}/dist/pyinstaller-macos-intel"
    DMG_STAGE="${PROJECT_ROOT}/build/macos-dmg-staging-intel"
    SPEC_FILE="${SCRIPT_DIR}/spec/KOLConnect_mac_intel.spec"
    DMG_PATH="${RELEASE_DIR}/KOLConnect_${VERSION}_mac_intel.dmg"
    ;;
  *)
    echo "Unsupported macOS architecture: ${TARGET_ARCH}. Use arm64 or x86_64." >&2
    exit 1
    ;;
esac

APP_PATH="${DIST_DIR}/KOLConnect.app"
APP_BINARY="${APP_PATH}/Contents/MacOS/KOLConnect"
export MACOSX_DEPLOYMENT_TARGET=12.0

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
if [[ "${ARCH}" != "${TARGET_ARCH}" || "${PYTHON_ARCH}" != "${TARGET_ARCH}" ]]; then
  echo "macOS ${TARGET_ARCH} build requires matching OS and Python runtimes." >&2
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

if [[ ! -x "${APP_BINARY}" ]]; then
  echo "Application binary is missing or not executable: ${APP_BINARY}" >&2
  exit 1
fi
BINARY_FILE_INFO="$(file "${APP_BINARY}")"
BINARY_ARCHES="$(lipo -archs "${APP_BINARY}")"
echo "Application binary: ${BINARY_FILE_INFO}"
echo "Application architectures: ${BINARY_ARCHES}"
if [[ "${BINARY_ARCHES}" != "${TARGET_ARCH}" ]]; then
  echo "Architecture mismatch: expected ${TARGET_ARCH}, found ${BINARY_ARCHES}." >&2
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
echo "CPU architecture: ${TARGET_ARCH}"
echo "Deployment target: ${MACOSX_DEPLOYMENT_TARGET}"
shasum -a 256 "${DMG_PATH}"
