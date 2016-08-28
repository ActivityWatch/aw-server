#!/bin/bash

# Used to create base .spec (needs manual modification)
# pyinstaller __main__.py -n aw-server

echo "Please make sure that ./aw_server/static contains the build from aw-webui"

pyinstaller aw-server.spec
