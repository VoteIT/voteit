#!/bin/bash
set -e
if [ $# -lt 1 ]; then
  echo "Usage: $0 <major|minor|patch|stable|post|alpha|beta|rc|dev> [alpha|beta|rc|dev]"
  echo "Bumps the version in pyproject.toml, then creates and pushes the matching git tag."
  echo "Uncommitted changes to CHANGELOG.md are committed along with the version bump."
  echo "A prerelease needs a release component too, e.g. '$0 minor rc' for 1.10.2 -> 1.11.0rc1."
  exit
fi
BUMP="$1"
PREID="$2"

# Warn about potential issues before tagging.
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color
warn() { echo -e "${YELLOW}WARNING: $1${NC}" >&2; }
error() { echo -e "${RED}ERROR: $1${NC}" >&2; }

if ! [[ "$BUMP" =~ ^(major|minor|patch|stable|post|alpha|beta|rc|dev)$ ]]; then
  error "<bump> must be one of major, minor, patch, stable, post, alpha, beta, rc, dev."
  exit 1
fi

BUMP_ARGS=(--bump "$BUMP")
if [ -n "$PREID" ]; then
  if ! [[ "$PREID" =~ ^(alpha|beta|rc|dev)$ ]]; then
    error "[preid] must be one of alpha, beta, rc, dev."
    exit 1
  fi
  BUMP_ARGS+=(--bump "$PREID")
fi

# A tag pointing at a commit that doesn't hold the code that was tested is worse
# than no tag at all. The changelog is the exception: it changes no code, and it
# is committed along with the version bump.
if [ -n "$(git status --porcelain -- . ':!CHANGELOG.md')" ]; then
  error "You have uncommitted changes other than CHANGELOG.md. Commit or stash them before tagging."
  exit 1
fi

CURRENT="$(uv version --short)" || { error "Failed to read the version from pyproject.toml."; exit 1; }
if ! [[ "$CURRENT" =~ ^[0-9]+\.[0-9]+\.[0-9]+ ]]; then
  error "No valid version in pyproject.toml (got '${CURRENT}')."
  exit 1
fi

# --frozen keeps the dry run from re-locking; the real bump below re-locks for real.
VERSION="$(uv version --dry-run --short --frozen "${BUMP_ARGS[@]}")" || {
  error "Failed to calculate the new version."
  exit 1
}
TAG="v$VERSION"

if git tag -l "$TAG" | grep -q "^$TAG$"; then
    error "Tag '$TAG' already exists."
    exit 1
fi

# Prereleases carry an 'rc1' style suffix and get no changelog entry of their own.
if [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  # A stable tag publishes a release image, so it may only be cut from main.
  BRANCH="$(git branch --show-current)"
  if [ "$BRANCH" != "main" ]; then
    error "Stable version ${VERSION} can only be tagged on main (on '${BRANCH:-detached HEAD}')."
    exit 1
  fi
  if ! grep -q "^## ${VERSION}\b" CHANGELOG.md; then
    warn "No changelog entry found for version ${VERSION} in CHANGELOG.md."
  fi
fi

echo "Current version: ${CURRENT}"
read -p "Do you want to bump to '${VERSION}' and push git tag '${TAG}' [y/N] " -n 1 -r
echo
if [[ "$REPLY" =~ ^[yY]$ ]]; then
  # Writes pyproject.toml and the project version in uv.lock; --no-sync leaves the
  # virtualenv alone, since nothing but our own version changed.
  uv version --no-sync "${BUMP_ARGS[@]}" > /dev/null || { error "Failed to bump version."; exit 1; }
  git commit -q pyproject.toml uv.lock CHANGELOG.md -m "Version bump to ${VERSION}" || { error "Failed to commit the version bump."; exit 1; }
  # An annotated tag is what --follow-tags carries along with the commit.
  git tag -a "$TAG" -m "$VERSION" || { error "Failed to create tag '${TAG}'."; exit 1; }
  git push --follow-tags origin HEAD || { error "Failed to push. The commit and tag '${TAG}' exist locally only."; exit 1; }
fi
