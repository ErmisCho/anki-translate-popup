---
id: TASK-19
title: 'Steady voice, with a female or male preference'
status: Done
assignee: []
created_date: '2026-07-28 18:02'
updated_date: '2026-07-28 18:08'
labels:
  - implemented
dependencies: []
ordinal: 4015
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The voice changes between selections: pickVoice returns the first voice whose language matches, so enumeration order decides, and a language with no installed voice silently falls to the online voice instead. Add voice_gender (female default, male, any), score candidates so the same voice is chosen every time for a language, and infer gender from the voice name since the Web Speech API does not expose it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The same language picks the same voice on every selection
- [x] #2 voice_gender female prefers a female voice, male a male one
- [x] #3 A language with no voice of that gender still speaks, using what exists
- [x] #4 Selectable from the gear menu as well as the config dialog
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Fixed: pickVoice scores every candidate and breaks ties on the name, so enumeration order no longer decides which voice speaks. voice_gender (female by default) prefers a gender, inferred from the voice name since the API does not expose it; region still outranks it, and preferred_voice outranks both. Known ceiling: the name table only knows the voices in it, and online audio has one voice per language.
<!-- SECTION:FINAL_SUMMARY:END -->
