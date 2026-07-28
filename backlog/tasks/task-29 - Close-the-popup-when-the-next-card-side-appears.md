---
id: TASK-29
title: Close the popup when the next card side appears
status: Done
assignee: []
created_date: '2026-07-28 20:26'
updated_date: '2026-07-28 20:26'
labels:
  - implemented
dependencies: []
ordinal: 14015
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The reviewer page is built once a session and cards are swapped inside it, so nothing ever closed the popup: it stayed over the next card showing a translation of words no longer on screen. Close it when a side appears - but only then, since the same card-text push is also made when a setting changes and when a pronounce key asks for text.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Answering a card closes the popup
- [x] #2 Revealing the answer closes it
- [x] #3 A gear toggle does not close it
- [x] #4 Pressing a pronounce key does not close it
<!-- AC:END -->



## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Fixed: _push_card_text takes new_side and marks the payload, and only _on_card_side_shown passes it. onCardText hides the popup on that flag alone, so the three other pushes - the settings re-push, the post-detection re-push and the pronounce-key reply - leave it alone. 373 tests, three new pinning which push may close it.
<!-- SECTION:FINAL_SUMMARY:END -->
