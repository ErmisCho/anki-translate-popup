---
id: TASK-24
title: A gear change must take effect on the spot
status: Done
assignee: []
created_date: '2026-07-28 19:00'
updated_date: '2026-07-28 19:00'
labels:
  - implemented
dependencies: []
ordinal: 9015
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
AddonManager.writeConfig only writes meta.json - aqt/addons.py fires the updated action from the config dialog alone - so a gear change reached nothing but the single field the page had already flipped for itself. A second open webview, the Qt shortcuts and the cache settings stayed on the old values until Anki restarted. Broadcast the change ourselves, and treat turning card speech on as a request to hear the card on screen rather than the next one.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Every open webview sees a gear change immediately
- [x] #2 Turning Speak the card as it appears on speaks the current card
- [x] #3 The once-per-side dedupe does not swallow that playback
- [x] #4 Turning an option off, or an unrelated toggle, speaks nothing
<!-- AC:END -->



## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Fixed: _apply_config_change is now called after this add-on's own writeConfig, not just from Anki's hook - verified against aqt/addons.py, where writeConfig writes meta.json and nothing more, and the updated action is fired only by the config dialog. The comment claiming otherwise is gone. Turning on either card-speech toggle also clears the once-per-side dedupe and speaks the card on screen, since the toggle is a request to hear this card rather than the next one. Follow-up after a report that it still did nothing: it spoke the side on screen, so turning it on with the answer showing and 'Also speak the answer' off hit the answer gate and stayed silent. It now speaks the side the setting governs - the prompt in that case - and turning either toggle off stops playback.
<!-- SECTION:FINAL_SUMMARY:END -->
