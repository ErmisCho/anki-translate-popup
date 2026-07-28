---
id: TASK-7
title: Cache example lookups
status: Done
assignee: []
created_date: '2026-07-28 17:07'
labels:
  - implemented
dependencies: []
references:
  - BACKLOG.md
ordinal: 7
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Persist non-empty Tatoeba example results with expiry and size limits.
<!-- SECTION:DESCRIPTION:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Completed: examples use a separate table in cache.sqlite with TTL, purge, clear, and row-cap behavior.
<!-- SECTION:FINAL_SUMMARY:END -->
