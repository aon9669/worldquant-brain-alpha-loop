#!/bin/bash
# Start/restart the MacBook WQ loop via launchd.
launchctl bootout gui/$(id -u)/com.aon.wqloop 2>/dev/null
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.aon.wqloop.plist && echo started
