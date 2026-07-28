---
id: TASK-26
title: Restrict automatic pronunciation to one language
status: Done
assignee: []
created_date: '2026-07-28 19:22'
updated_date: '2026-07-28 19:24'
labels:
  - implemented
dependencies: []
ordinal: 11015
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Not every language on a card is worth hearing: an English definition under a German headword is read out for no benefit, and a misdetection makes it worse. Add speak_only_language - empty for all, or one code - which filters automatic speech only. Pressing Pronounce, x or c stays an explicit request and is never filtered.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 With it set to de, an English line is not spoken automatically
- [x] #2 Pressing Pronounce on English text still speaks it
- [x] #3 Empty means every language, as now
- [x] #4 Settable from the gear menu
<!-- AC:END -->



## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Implemented: speak_only_language, empty for all, filters automatic speech only - card auto-pronounce drops segments in other languages, and auto-pronounce-on-selection skips them, while the Pronounce button and the pronounce keys are untouched. On the gear as 'Speak only' with All at the top. Card speech also logs each line and the language chosen for it under debug_logging, so a misdetection can be reported precisely.
<!-- SECTION:FINAL_SUMMARY:END -->
