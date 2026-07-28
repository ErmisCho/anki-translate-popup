---
id: TASK-27
title: Give the gear menu its own polished surface
status: Done
assignee: []
created_date: '2026-07-28 19:58'
updated_date: '2026-07-28 19:59'
labels:
  - implemented
dependencies: []
ordinal: 12015
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The dropdown drew itself in the popup's own background, so a panel floating above the popup looked like part of it. Give the menu its own surface variables: near-black in dark mode, a lit inset top edge so it does not read as a hole, a deeper shadow, rounder corners, larger hit areas, hover and active transitions, and one hairline separating the switches from the pickers.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The menu is visibly a separate surface from the popup
- [x] #2 Switches and pickers read as two groups
- [x] #3 Light mode stays light and uncluttered
<!-- AC:END -->



## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Done: four menu-scoped custom properties per theme (--atp-menu-bg, -line, -ring, -shadow), near-black #0b0c0f in dark mode against the popup's #2b2f36, with an inset top hairline so the panel reads as lit rather than punched out. Rows gained padding, a 7px radius and a 120ms hover transition, and one border separates the switches from the pickers. Verified by rendering the real stylesheet with the real menu markup in Chrome, both themes.
<!-- SECTION:FINAL_SUMMARY:END -->
