---
id: TASK-18
title: 'Detect the language of every selection, not just the first'
status: Done
assignee: []
created_date: '2026-07-28 18:02'
updated_date: '2026-07-28 18:08'
labels:
  - implemented
dependencies: []
ordinal: 3015
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
With source_language auto, the popup speaks a new selection in the previously detected language: show() calls pronounce() immediately while requestTranslation() is still in flight, so detectedSource still holds the last selection's language. Select German then English and both are read with the German voice. Reset the detection per selection, hold auto-pronounce until the provider names the language, and make the header show that auto is still in force rather than looking as though the pair switched.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Selecting German then English speaks each in its own language
- [x] #2 A stale detection is never reused for a new selection
- [x] #3 The source stays auto in the config; only the display names what was detected
- [x] #4 With auto_translate off nothing is sent merely to detect a language
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Fixed: detectedSource is cleared for each selection, and auto-pronounce waits for the provider to name the language instead of speaking with the previous one. The header shows AUTO or AUTO-DE, so a detection never reads as the pair having changed. With auto_translate off nothing is sent to detect: speech falls back to speech_language.
<!-- SECTION:FINAL_SUMMARY:END -->
