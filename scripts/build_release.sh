#!/bin/bash
set -e

# ANNY Runtime Release Builder
# This script bundles the repository into a distributable artifact mapped to a durable Git commit.

# Move to repo root
cd "$(dirname "$0")/.."

# Check if inside a git repository
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "Error: Not inside a git repository. Release builds must map to a durable Git commit."
    exit 1
fi

if [ -n "$(git status --porcelain)" ]; then
    echo "Error: Working tree is dirty. Release builds must be performed on a clean, committed state."
    exit 1
fi

COMMIT_SHA=$(git rev-parse HEAD)
SHORT_SHA=${COMMIT_SHA:0:7}
BUILD_TIME=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

VERSION_FILE="runtime/core/version.py"
if [ ! -f "$VERSION_FILE" ]; then
    echo "Error: $VERSION_FILE not found."
    exit 1
fi

VERSION=$(python3 -I -c 'import runpy, sys; print(runpy.run_path(sys.argv[1])["__version__"])' "$VERSION_FILE") || {
    echo "Error: canonical Runtime version could not be loaded."
    exit 1
}
if [ -z "$VERSION" ]; then
    echo "Error: canonical Runtime version is empty."
    exit 1
fi

RELEASE_NAME="ANNY-RUNTIME-v${VERSION}-${SHORT_SHA}"
BUILD_DIR="/tmp/${RELEASE_NAME}_build"

echo "Building release: $RELEASE_NAME"
echo "Commit: $COMMIT_SHA"

# 1. Clean previous build
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

# 2. Export clean repository
git archive HEAD | tar -x -C "$BUILD_DIR"

# 3. Burn identity into version.py
TARGET_VERSION_FILE="$BUILD_DIR/runtime/core/version.py"
sed -i "s/__commit__ =.*/__commit__ = \"$COMMIT_SHA\"/" "$TARGET_VERSION_FILE"
sed -i "s/__build_time__ =.*/__build_time__ = \"$BUILD_TIME\"/" "$TARGET_VERSION_FILE"

# 4. Create Tarball
TARBALL_NAME="${RELEASE_NAME}.tar.gz"
echo "Creating $TARBALL_NAME..."
cd "/tmp"
tar -czf "$TARBALL_NAME" "${RELEASE_NAME}_build"
cd - > /dev/null

mv "/tmp/$TARBALL_NAME" ./
echo "Generated release artifact: $TARBALL_NAME"

# 5. Generate checksum
sha256sum "$TARBALL_NAME" > "${TARBALL_NAME}.sha256"
echo "Generated checksum: ${TARBALL_NAME}.sha256"

# 6. Cleanup
rm -rf "$BUILD_DIR"

echo "Release build complete."
