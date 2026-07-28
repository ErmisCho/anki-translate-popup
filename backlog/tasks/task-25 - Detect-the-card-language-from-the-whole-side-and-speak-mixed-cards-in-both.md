---
id: TASK-25
title: 'Detect the card language from the whole side, and speak mixed cards in both'
status: Done
assignee: []
created_date: '2026-07-28 19:16'
updated_date: '2026-07-28 19:18'
labels:
  - implemented
dependencies: []
ordinal: 10015
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
die Aktie, -n was detected as not German by card auto-pronounce while the same words selected in the popup were spoken correctly: detection ran on the spoken excerpt alone, which for a headword line is a few ambiguous characters. Detect from the whole card side instead. Separately, a side is not one language - a German headword can be followed by an English definition, and both are currently read by one voice.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A short headword line is detected from the whole side, not from itself
- [x] #2 A German line followed by an English line is spoken in both voices
- [x] #3 Consecutive lines in one language stay a single clip
- [x] #4 A line too short to judge follows the language of the side
<!-- AC:END -->



## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Fixed: detection now runs on the whole card side rather than the spoken excerpt, so a headword line is identified by the card it belongs to. _speech_segments then splits a side into runs of one language - a line of 25 characters or more is detected on its own, anything shorter follows the side - and each run is synthesised separately and queued in order. Consecutive lines of one language stay a single clip, so an ordinary card still costs one request. Only applies when the pair leaves the language open.
<!-- SECTION:FINAL_SUMMARY:END -->
