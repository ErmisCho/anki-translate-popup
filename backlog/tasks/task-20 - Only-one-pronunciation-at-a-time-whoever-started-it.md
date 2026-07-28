---
id: TASK-20
title: 'Only one pronunciation at a time, whoever started it'
status: Done
assignee: []
created_date: '2026-07-28 18:13'
updated_date: '2026-07-28 18:14'
labels:
  - implemented
dependencies: []
ordinal: 5015
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Card auto-pronounce is queued by Python through av_player and never tells the page, so onlineSpeechActive is false for it and stopSpeech skips the bridge call. A card clip therefore keeps playing underneath a popup pronunciation. The reverse also overlaps: a new card side arrives while the page is still speaking the previous one. Every new pronunciation must silence whatever is playing, from either side.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Selecting text while card audio plays stops the card audio first
- [x] #2 A new card side stops speech left over from the previous card
- [x] #3 Pressing Pronounce twice quickly still leaves only the second speaking
- [x] #4 Closing the popup does not cut off audio the popup never started
<!-- AC:END -->



## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Fixed: the stop is now split three ways. stopBrowserSpeech cancels only the page's own speech and runs when a new card side arrives; stopAllSpeech also clears Anki's audio queue and runs for every new pronunciation and the stop key; stopSpeech stays conditional so closing the popup cannot cut off audio the popup never started.
<!-- SECTION:FINAL_SUMMARY:END -->
