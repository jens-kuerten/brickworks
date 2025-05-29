#!/bin/bash

set -e

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 [patch|minor|major]"
  exit 1
fi

BUMP_TYPE=$1

# Get latest version tag (format: vX.Y.Z)
LATEST_TAG=$(git tag --list 'v*' --sort=-v:refname | head -n1)
if [[ -z "$LATEST_TAG" ]]; then
  MAJOR=0; MINOR=0; PATCH=0
else
  VERSION=${LATEST_TAG#v}
  IFS='.' read -r MAJOR MINOR PATCH <<< "$VERSION"
fi

case $BUMP_TYPE in
  patch)
    PATCH=$((PATCH + 1))
    ;;
  minor)
    MINOR=$((MINOR + 1))
    PATCH=0
    ;;
  major)
    MAJOR=$((MAJOR + 1))
    MINOR=0
    PATCH=0
    ;;
  *)
    echo "Unknown bump type: $BUMP_TYPE"
    exit 1
    ;;
esac

NEW_VERSION="$MAJOR.$MINOR.$PATCH"
NEW_TAG="v$NEW_VERSION"

git tag "$NEW_TAG"
echo "Tagged new version: $NEW_TAG"
git push origin "$NEW_TAG"
echo "Pushed tag to remote repository."
