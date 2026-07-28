---
id: TASK-28
title: 'Popup shares the menu palette, and a theme that can be forced'
status: Done
assignee: []
created_date: '2026-07-28 20:06'
updated_date: '2026-07-28 20:06'
labels:
  - implemented
dependencies: []
ordinal: 13015
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The gear menu got its own near-black surface while the popup stayed the old mid-grey, so the two no longer looked related. Bring the popup into the same family, a shade above the menu so the menu still reads as a panel in front of it. Add theme - auto, dark, light - so the popup can be dark on a light collection without touching the card.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Popup and menu read as one palette in dark mode
- [x] #2 theme light forces light even in night mode, menu included
- [x] #3 theme dark forces dark on a light collection
- [x] #4 auto still follows Anki live
<!-- AC:END -->



## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Done: the dark palette is now #131418 for the popup against the menu's #0b0c0f, one family with the menu still a shade darker so it reads as a panel in front. theme (auto/dark/light) puts a class on the popup element only, never on Anki's document; the dark block is scoped :not(.atp-theme-light) so forcing light needs no duplicate variable list, it falls through to the light defaults. Verified in Chrome: forced light renders light on a night-mode page, menu included.
<!-- SECTION:FINAL_SUMMARY:END -->
