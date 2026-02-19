#!/bin/bash

SOURCE="/DIR/LINUX/"
DEST="/REMOTE_DIR/LINUX"

FORCE=0

for arg in "$@"; do
	if [[ "$arg" == "--force" ]]; then
		FORCE=1
	else
		echo "Unknown argument: $arg"
		echo "Usage: $0 --force"
		exit 1
	fi
done

if [[ $FORCE -eq 0 ]]; then
	echo "No --force argument supplied."
	echo "Dry-run only. To perform the backup, run: $0 --force"
	DRY_RUN="--dry-run"
else
	DRY_RUN=""
	echo "FORCE flag detected: executing backup!"
fi

# Safety check: ensure source exists and is mounted
if [ ! -d "$SOURCE" ]; then
    echo "ERROR: Source directory does not exist: $SOURCE"
    exit 1
fi

# Safety check: prevent empty SOURCE variable disasters
if [ -z "$SOURCE" ] || [ -z "$DEST" ]; then
    echo "ERROR: SOURCE or DEST variable is empty."
    exit 1
fi

echo "Starting rsync backup..."
echo "Source:      $SOURCE"
echo "Destination: $DEST"
echo

rsync -rtvhc $DRY_RUN \
       --delete \
       --itemize-changes \
       --progress \
       "$SOURCE" \
       "$DEST"

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
	echo
	echo "Backup completed successfully."
else
	echo
	echo "Backup finished with errors (exit code $EXIT_CODE)."
fi

exit $EXIT_CODE

