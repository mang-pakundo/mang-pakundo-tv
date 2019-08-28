#!/bin/bash

source .env
VER=$2
PLUGIN=${1%/}
if [ -z "$RELEASE_DIR" ]; then
    echo "Release dir not found."
    exit 1
fi

if [ -z "$VER" ] || [ -z "$PLUGIN" ]; then
    echo "Usage: mkrelease.sh <PLUGIN> <VERSION>"
    exit 1
fi

REPLACE_TPL="<addon id=\"$PLUGIN\" name=\"naIsko\" version=\"__VER__\" provider-name=\"mang.pakundo\">"
FIND_STR=$(echo $REPLACE_TPL | sed 's/__VER__/[0-9]+\\.[0-9]+\\.[0-9]+/')
REPLACE_STR=$(echo $REPLACE_TPL | sed "s/__VER__/$VER/")

echo "$RELEASE_DIR/$PLUGIN/$PLUGIN-$VER.zip"

sed -i .bak -E "s/$FIND_STR/$REPLACE_STR/" addons.xml
sed -i .bak -E "s/$FIND_STR/$REPLACE_STR/" $PLUGIN/addon.xml
md5sum addons.xml > addons.xml.md5

rm addons.xml.bak
rm "$PLUGIN/addon.xml.bak"
zip -r "$RELEASE_DIR/$PLUGIN/$PLUGIN-$VER.zip" "$PLUGIN"


echo "Go ahead and commit and push the release artifact"
echo "Then commit and push the version bump"