---
id: TASK-30
title: 'Identify a card side by the whole side, everywhere'
status: Done
assignee: []
created_date: '2026-07-28 20:42'
updated_date: '2026-07-28 20:42'
labels:
  - implemented
dependencies: []
ordinal: 15015
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Two defects behind der Aspekt, -e being spoken in the wrong language by the pronounce keys. The whole-side detection added earlier never applied under the default first-line scope, because the lines were trimmed before the detector saw them - so the side it identified was the bare headword. And the keys looked their detection up under the spoken excerpt while the card path stored it under the joined side, so the lookup missed every time and fell back.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 First-line scope still identifies the side by all of its lines
- [x] #2 x and c find the detection the card stored
- [x] #3 The provider is asked once per side, not once per path
<!-- AC:END -->



## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Fixed: _speech_segments takes an explicit context - the whole side - so trimming the spoken lines to the first no longer trims what the detector sees. _push_card_text looks the detection up by that same joined side rather than by the excerpt it is about to speak, so the pronounce keys find what the card stored instead of missing and falling back. Two tests: one asserts the headword alone is never the detection sample, the other that both paths use one key.
<!-- SECTION:FINAL_SUMMARY:END -->
