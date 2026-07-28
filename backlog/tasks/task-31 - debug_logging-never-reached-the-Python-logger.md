---
id: TASK-31
title: debug_logging never reached the Python logger
status: Done
assignee: []
created_date: '2026-07-28 21:10'
updated_date: '2026-07-28 21:10'
labels:
  - implemented
dependencies: []
ordinal: 16015
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The setting was forwarded to the webview as debug, turning on the page's console output, and nothing ever set the level of the add-on's own logger. Every logger.debug call in __init__.py was discarded regardless of the setting, so the documented way to diagnose a problem produced a log containing only 'loaded' lines - including the diagnostics added specifically to chase a report.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Turning debug_logging on puts the logger at DEBUG
- [x] #2 Turning it off returns it to INFO
- [x] #3 It takes effect on change, without a restart
<!-- AC:END -->



## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Fixed: _apply_log_level sets the add-on logger to DEBUG or INFO from the setting, called at setup and again from _apply_config_change so it takes effect the moment it is changed. Found while chasing a speech report - the log the user was asked to produce contained only 'loaded' lines, because the Python side had never honoured the flag.
<!-- SECTION:FINAL_SUMMARY:END -->
