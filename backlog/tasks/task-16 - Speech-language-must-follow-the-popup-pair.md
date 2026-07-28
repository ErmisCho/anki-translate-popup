---
id: TASK-16
title: Speech language must follow the popup pair
status: Done
assignee: []
created_date: '2026-07-28 17:45'
updated_date: '2026-07-28 17:51'
labels:
  - implemented
dependencies: []
ordinal: 1015
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
With the pair set to EN to EN (or auto), pressing Pronounce still speaks with a German voice: the voice comes from the global speech_language rather than the language of the text being spoken. Derive the speaking language from the effective source language of the popup, keeping the configured region when the base language matches (de -> de-DE), and fall back to speech_language only when the source is unknown.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Pronouncing an EN source speaks with an English voice, not a German one
- [x] #2 A de-AT speech_language still wins for a de source
- [x] #3 Per-deck and header language changes take effect without reopening the popup
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Fixed: pronounce() now derives the language from the popup's pair rather than the global speech_language, keeping a configured region when it is the same language. Computed in the page rather than pushed from Python, so a header change applies to the very next keypress. Known gap: a selection taken from the answer side is still spoken as the source language.
<!-- SECTION:FINAL_SUMMARY:END -->
