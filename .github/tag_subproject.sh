#!/bin/bash

TAG_NAME="$1"

if [ -z "$TAG_NAME" ]; then
  echo "Error: No tag name provided."
  echo "Usage: $0 <tag-name>"
  exit 1
fi

echo "Applying tag: $TAG_NAME to all subprojects..."

# Function to process each project
process_project() {
  local project_dir=$(pwd)
  local project_name=$(basename "$project_dir")
  
  echo -e "\n\033[1mProcessing project: $project_name\033[0m"
  echo "Project path: $project_dir"
  
  # Get the name of the default remote
  REMOTE_NAME=$(git remote | head -n 1)
  if [ -z "$REMOTE_NAME" ]; then
    echo "  ⚠️ No remotes found - skipping"
    return 1
  fi

  echo "  Remote: $REMOTE_NAME ($(git remote get-url "$REMOTE_NAME" | sed 's/git@github.com:/https:\/\/github.com\//'))"

  # Check if tag exists locally
  if git rev-parse "$TAG_NAME" >/dev/null 2>&1; then
    echo "  ✅ Tag exists locally"
    TAG_EXISTS=true
  else
    TAG_EXISTS=false
  fi

  # Check if tag exists on remote
  echo "  Checking remote for tag..."
  git fetch --tags --quiet
  if git ls-remote --tags "$REMOTE_NAME" | grep -q "refs/tags/$TAG_NAME$"; then
    echo "  ✅ Tag exists on remote"
    REMOTE_TAG_EXISTS=true
  else
    REMOTE_TAG_EXISTS=false
  fi

  if $TAG_EXISTS && $REMOTE_TAG_EXISTS; then
    echo "  🔄 Tag exists both locally and remotely - pushing to ensure sync"
    git push "$REMOTE_NAME" "$TAG_NAME" 2>&1 | sed 's/^/    /'
    echo "  ✔️ Sync complete"
    return 0
  fi

  if $REMOTE_TAG_EXISTS; then
    echo "  🔄 Tag exists on remote but not locally - fetching..."
    git fetch "$REMOTE_NAME" tag "$TAG_NAME" 2>&1 | sed 's/^/    /'
    git tag "$TAG_NAME" FETCH_HEAD
    echo "  ✔️ Tag fetched locally"
    return 0
  fi

  if ! $TAG_EXISTS && ! $REMOTE_TAG_EXISTS; then
    echo "  🆕 Creating new tag..."
    
    LAST_TAG=$(git describe --tags --abbrev=0 2>/dev/null)
    if [ $? -ne 0 ] || [ -z "$LAST_TAG" ]; then
      echo "  ℹ️ No previous tags found - creating initial tag"
      TAG_MESSAGE="Release: $TAG_NAME\n\nNo previous tags found. Initial release for the project."
    else
      echo "  ℹ️ Last tag found: $LAST_TAG"
      
      REPO_URL=$(git remote get-url "$REMOTE_NAME" | sed -e "s/\.git$//" -e "s/git@github.com:/https:\/\/github.com\//")
      COMPARE_URL="$REPO_URL/compare/$LAST_TAG...$TAG_NAME"

      COMMIT_LOG=$(git log "$LAST_TAG..HEAD" --oneline --pretty=format:"* %h %s")
      if [ -z "$COMMIT_LOG" ]; then
        TAG_MESSAGE="Release: $TAG_NAME\n\nNo new commits since the previous tag: $LAST_TAG."
      else
        TAG_MESSAGE="Release: $TAG_NAME\n\n**Changes since $LAST_TAG:**\n\nFullChangelog: $COMPARE_URL\n\n$COMMIT_LOG"
      fi
    fi

    git tag -a "$TAG_NAME" -m "$(echo -e "$TAG_MESSAGE")" 2>&1 | sed 's/^/    /'
    if [ ${PIPESTATUS[0]} -ne 0 ]; then
      echo "  ❌ Error creating tag"
      return 1
    fi
    echo "  ✔️ Tag created locally"
  fi

  # Push the tag with progress
  echo "  🚀 Pushing tag to remote..."
  git push "$REMOTE_NAME" "$TAG_NAME" 2>&1 | sed 's/^/    /'
  
  if [ ${PIPESTATUS[0]} -ne 0 ]; then
    echo "  ❌ Error pushing tag"
    return 1
  fi
  
  echo "  ✔️ Successfully pushed tag"
  return 0
}

# Execute for all projects with immediate output
while IFS= read -r project; do
  (
    cd "$project" || exit
    process_project
    echo "----------------------------------------"
  )
done < <(~/.bin/repo list --group sdk,canmv -p)

echo -e "\nTagging completed for all subprojects."
