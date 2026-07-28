---
id: TASK-32
title: A reversed card was spoken with its languages swapped
status: Done
assignee: []
created_date: '2026-07-28 21:17'
updated_date: '2026-07-28 21:17'
labels:
  - implemented
dependencies: []
ordinal: 17015
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From a debug log: the English prompt of a reversed card was spoken in de-DE and its German answer in en. Front-is-source and back-is-target only holds for a card laid out the way the pair describes; reversed, the assumption is exactly backwards, and nothing corrected it because the front had no cached detection and the back never asked for one. A side whose language the user has not pinned is now checked against its own text before it is spoken.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A reversed card speaks each side in its own language
- [x] #2 A pinned front or back language is taken at its word, with no request
- [x] #3 Normal cards still speak correctly
- [x] #4 The check happens on the worker thread, only for keys the user pressed
<!-- AC:END -->



## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Fixed: _push_card_text marks each side as guessed when its voice language is auto, the page passes that through the speak command, and _start_speech identifies the text inside the QueryOp it already runs before synthesising. Cached, worker-thread, and only for an explicit keypress. Pinning front_speech_language or back_speech_language opts out. Found from a debug log rather than by inference, after the logging defect in TASK-31 was fixed.
<!-- SECTION:FINAL_SUMMARY:END -->
