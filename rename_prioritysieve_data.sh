#!/usr/bin/env bash
# Rename legacy AnkiMorphs data files and directories to the new PrioritySieve names.
# Run from your Anki2 directory:  bash rename_prioritysieve_data.sh

set -euo pipefail

# mapping of old -> new names inside each profile directory
declare -A RENAME_MAP=(
  ["ankimorphs_profile_settings.json"]=prioritysieve_profile_settings.json
  ["ankimorphs_extra_settings.ini"]=prioritysieve_extra_settings.ini
  ["known-morphs"]=prioritysieve-known-morphs
  ["priority-files"]=prioritysieve-priority-files
)

# directories within Anki2 that are not profiles and should be skipped
SKIP_DIRS=("addons21" "backups" "collection.media" "collection.media.strings" "collection.anki2" "log" ".git")

is_profile_dir() {
  local name=$1
  for skip in "${SKIP_DIRS[@]}"; do
    if [[ $name == "$skip" ]]; then
      return 1
    fi
  done
  [[ -d $name ]]
}

echo "Scanning profiles under: $(pwd)"

shopt -s nullglob
declare -a profiles=()
for entry in *; do
  if is_profile_dir "$entry"; then
    profiles+=("$entry")
  fi
done

if [[ ${#profiles[@]} -eq 0 ]]; then
  echo "No profile directories found. Run this script from your Anki2 directory."
  exit 1
fi

for profile in "${profiles[@]}"; do
  echo
  echo "=== Profile: $profile ==="
  for old_name in "${!RENAME_MAP[@]}"; do
    new_name=${RENAME_MAP[$old_name]}
    old_path="$profile/$old_name"
    new_path="$profile/$new_name"

    if [[ ! -e $old_path ]]; then
      continue
    fi

    if [[ -e $new_path ]]; then
      echo "  ! Skipping: $new_path already exists (kept $old_path)"
      continue
    fi

    echo "  → Renaming $old_path -> $new_path"
    mv "$old_path" "$new_path"
  done
done

echo
echo "Done. Launch PrioritySieve to verify the migrated data."
