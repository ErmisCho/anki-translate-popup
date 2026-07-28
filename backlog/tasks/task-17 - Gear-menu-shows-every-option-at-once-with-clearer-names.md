---
id: TASK-17
title: 'Gear menu shows every option at once, with clearer names'
status: Done
assignee: []
created_date: '2026-07-28 17:45'
updated_date: '2026-07-28 17:51'
labels:
  - implemented
dependencies: []
ordinal: 2015
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The gear drop menu hides its options behind a small scrolling list and the labels are terse and inconsistent. Show every item at once without scrolling, and rename the options so each one reads as what it does rather than as the config key behind it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Every gear option is visible at once, no scrolling
- [x] #2 The menu still fits inside the reviewer window near a bottom-edge selection
- [x] #3 Labels say what the option does, and match the wording used in config.md
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Fixed: the settings menu drops the 13.5em scroll cap that the language lists still need, and flips above the gear when the window is too short. Labels now read as actions and match config.md, so '…also the answer' no longer depends on the row above it.
<!-- SECTION:FINAL_SUMMARY:END -->
