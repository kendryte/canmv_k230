#!/bin/bash

# Set the tag to be applied to all subprojects
TAG_NAME="$1"

if [ -z "$TAG_NAME" ]; then
  echo "Error: No tag name provided."
  echo "Usage: ./$0 <tag-name>"
  exit 1
fi

echo "Applying tag: $TAG_NAME to all subprojects..."

# Iterate over all subprojects and apply the tag
~/.bin/repo forall --group sdk,canmv -c '
  echo "Tagging project $(pwd)"
  set -x

  # Get the name of the default remote (typically 'origin')
  REMOTE_NAME=$(git remote | head -n 1)

  if [ -z "$REMOTE_NAME" ]; then
    echo "Error: No remotes found."
    exit 1
  fi

  # Apply the tag to the current project
  git tag -a '"$TAG_NAME"' -m "Tagging for release version '"$TAG_NAME"'"
  if [ $? -ne 0 ]; then
    echo "Error creating tag in $(pwd)"
    exit 1
  fi

  # Push the tag to the remote repository
  echo "Push tag to $REMOTE_NAME"

  git push -v $REMOTE_NAME '"$TAG_NAME"'
  if [ $? -ne 0 ]; then
    echo "Error pushing tag in $(pwd)"
    exit 1
  fi

  echo "Tag applied and pushed to $(git remote get-url $REMOTE_NAME)"
'

echo "Tagging completed for all subprojects."
