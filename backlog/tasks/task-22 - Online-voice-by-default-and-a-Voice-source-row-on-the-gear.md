---
id: TASK-22
title: 'Online voice by default, and a Voice source row on the gear'
status: Done
assignee: []
created_date: '2026-07-28 18:31'
updated_date: '2026-07-28 18:32'
labels:
  - implemented
dependencies: []
ordinal: 7015
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
A card can only ever use the online voice (Chromium needs a user gesture the reviewer cannot give), so under tts_provider auto a selection found a system voice and a card did not - the same word in two voices, the card's noticeably more natural. Default to google_unofficial so both match, expose it on the gear, and make enable_google_unofficial actually cover audio: config.md promises it blocks all traffic to the endpoint, but only the translation factory ever consulted it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A selection and a card of the same word use the same voice
- [x] #2 tts_provider is settable from the gear menu
- [x] #3 enable_google_unofficial false blocks new audio, naming the switch
- [x] #4 Audio already cached still plays when the switch is off
<!-- AC:END -->



## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Done: tts_provider defaults to google_unofficial in config.json, config.py and the page's own DEFAULTS, and is on the gear as Voice source (Online / System, else online / System only). Also fixed a promise config.md was already breaking: enable_google_unofficial now gates _synthesize_blocking, the single choke point for all online audio, placed after the cache check so a clip on disk still plays and only new traffic is refused. Documented the cost plainly - nothing is spoken offline under the new default, and voice_gender and preferred_voice stop applying.
<!-- SECTION:FINAL_SUMMARY:END -->
