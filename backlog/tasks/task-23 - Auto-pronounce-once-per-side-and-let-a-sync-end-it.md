---
id: TASK-23
title: 'Auto-pronounce once per side, and let a sync end it'
status: Done
assignee: []
created_date: '2026-07-28 18:38'
updated_date: '2026-07-28 18:39'
labels:
  - implemented
dependencies: []
ordinal: 8015
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Anki re-emits its reviewer hooks whenever the page is rebuilt, so a sync, an edit or the More menu spoke the card a second time - the two-second dedupe window was there to catch this and only caught the fast cases. Dedupe on the card side itself instead, stop audio when a sync starts, and give the x and c shortcuts the same detected language the card was spoken in rather than the global fallback.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A rebuild never re-speaks the card, however long after
- [x] #2 Answering and meeting the card again does speak it
- [x] #3 Starting a sync stops the audio and does not restart it
- [x] #4 x and c speak in the language the card itself was spoken in
<!-- AC:END -->



## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Fixed: the dedupe is now identity-based - the last (card id, side) auto-spoken, with no clock - so a rebuild never re-speaks however long after, while answering and meeting the card again still does. sync_will_start stops playback, registered through getattr so an older Anki without the hook still loads. _push_card_text resolves x and c through the same detection the card used, read from the cache only, since it runs on the UI thread. Known gap documented: with auto_pronounce_card off nothing fills that cache and the shortcuts fall back to speech_language.
<!-- SECTION:FINAL_SUMMARY:END -->
