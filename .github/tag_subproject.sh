#!/bin/bash

# Set the tag to be applied to all subprojects
TAG_NAME="$1"

if [ -z "$TAG_NAME" ]; then
  echo "Error: No tag name provided."
  echo "Usage: $0 <tag-name>"
  exit 1
fi

echo "Applying tag: $TAG_NAME to all subprojects..."

# Iterate over all subprojects and apply the tag
~/.bin/repo forall --group sdk,canmv -c '
  echo "Processing project $(pwd)"
  set -x

  # Get the name of the default remote (typically "origin")
  REMOTE_NAME=$(git remote | head -n 1)

  if [ -z "$REMOTE_NAME" ]; then
    echo "Error: No remotes found."
    exit 1
  fi

  # Get the last tag from the repository
  LAST_TAG=$(git describe --tags --abbrev=0 2>/dev/null)
  if [ $? -ne 0 ] || [ -z "$LAST_TAG" ]; then
    echo "No previous tags found. Creating tag without commit history in $(pwd)..."
    LAST_TAG=""
    TAG_MESSAGE="Release: '"$TAG_NAME"'\n\nNo previous tags found. Initial release for the project."
  else
    echo "Last tag found: $LAST_TAG"

    # Collect commits between the last tag and the current HEAD
    COMMIT_LOG=$(git log "$LAST_TAG..HEAD" --oneline --pretty=format:"* %h %s")
    if [ -z "$COMMIT_LOG" ]; then
      TAG_MESSAGE="Release: '"$TAG_NAME"'\n\nNo new commits since the previous tag: $LAST_TAG."
    else
      TAG_MESSAGE="Release: '"$TAG_NAME"'\n\n**Changes since $LAST_TAG:**\n\n$COMMIT_LOG"
    fi
  fi

  # Apply the new tag to the current project
  git tag -a '"$TAG_NAME"' -m "$(echo "$TAG_MESSAGE")"
  if [ $? -ne 0 ]; then
    echo "Error creating tag in $(pwd)"
    exit 1
  fi

  # Push the new tag to the remote repository
  echo "Pushing tag to $REMOTE_NAME"
  git push -v $REMOTE_NAME '"$TAG_NAME"'
  if [ $? -ne 0 ]; then
    echo "Error pushing tag in $(pwd)"
    exit 1
  fi

  echo "Tag applied and pushed to $(git remote get-url $REMOTE_NAME)"
'

echo "Tagging completed for all subprojects."
