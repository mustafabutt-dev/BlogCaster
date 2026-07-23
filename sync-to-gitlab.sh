#!/bin/bash
# sync-to-gitlab.sh — syncs new commits to GitLab with original authorship.
# published_record.json is excluded from patching and synced by wholesale
# overwrite instead — it's auto-generated data that scheduled GitHub Actions
# runs append to independently, so it drifts between conversations in ways
# a line-based patch can't reliably apply.
# Run after pushing to GitHub.

GITHUB_REPO=/Users/mustafa/Desktop/socialAgent
GITLAB_REPO=/Users/mustafa/Desktop/blogCaster-gitlab/BlogCaster
RECORDS_FILE=content/records/published_record.json

cd "$GITHUB_REPO" || exit 1
mkdir -p /tmp/lab-patches && rm -f /tmp/lab-patches/*.patch

git format-patch lab-sync..main -o /tmp/lab-patches --quiet -- . ":(exclude)$RECORDS_FILE"

PATCH_COUNT=0
if [ -n "$(ls -A /tmp/lab-patches 2>/dev/null)" ]; then
  PATCH_COUNT=$(ls /tmp/lab-patches/*.patch | wc -l | tr -d ' ')
  cd "$GITLAB_REPO" || exit 1
  git am /tmp/lab-patches/*.patch || {
    echo "⚠️  Patch conflict — resolve the file, then: git am --continue && git push"
    echo "    (or abort with: git am --abort)"
    exit 1
  }
  cd "$GITHUB_REPO" || exit 1
fi

RECORDS_UPDATED=0
if ! diff -q "$RECORDS_FILE" "$GITLAB_REPO/$RECORDS_FILE" > /dev/null 2>&1; then
  cp "$RECORDS_FILE" "$GITLAB_REPO/$RECORDS_FILE"
  cd "$GITLAB_REPO" || exit 1
  git add "$RECORDS_FILE"
  git commit -m "Sync published_record.json from GitHub" --quiet
  RECORDS_UPDATED=1
  cd "$GITHUB_REPO" || exit 1
fi

if [ "$PATCH_COUNT" -eq 0 ] && [ "$RECORDS_UPDATED" -eq 0 ]; then
  echo "Nothing new to sync"
  rm -rf /tmp/lab-patches
  exit 0
fi

cd "$GITLAB_REPO" || exit 1
git push

cd "$GITHUB_REPO" || exit 1
git tag -f lab-sync main
rm -rf /tmp/lab-patches

SUMMARY="Synced $PATCH_COUNT commits to GitLab"
if [ "$RECORDS_UPDATED" -eq 1 ]; then
  SUMMARY="$SUMMARY + published_record.json catch-up"
fi
echo "✅ $SUMMARY"
