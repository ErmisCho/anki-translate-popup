---
id: TASK-21
title: Card auto-pronounce detects the language when nothing names it
status: Done
assignee: []
created_date: '2026-07-28 18:23'
updated_date: '2026-07-28 18:23'
labels:
  - implemented
dependencies: []
ordinal: 6015
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
With source_language auto, speech_language_for falls back to the global speech_language, so an English card is read by a German voice. Ask the translation provider to identify the card side and use that, cached, with the configured region preserved.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 An English card under an auto pair is spoken in English
- [x] #2 A card costs at most one detection request, however often it is reviewed
- [x] #3 A failed detection still speaks, using speech_language
- [x] #4 Pinning front_speech_language or a real source_language avoids detection entirely
<!-- AC:END -->



## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Implemented: Translator.detect asks the provider by translating a 200-character sample with source auto, which is the detection every provider already performs. Results are cached in a detections table beside translations and examples, scoped by provider and subject to the same TTL and row cap. Card auto-pronounce resolves its language inside the worker thread only when speech_language_needs_detection says nothing else names one, and falls back to speech_language on failure. Documented as the one case where card auto-pronounce transmits unselected text.
<!-- SECTION:FINAL_SUMMARY:END -->
