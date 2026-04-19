# Project Instructions

## Stack
- Package manager: pnpm
- Lint: eslint
- Typecheck: tsc --noEmit
- Unit test: vitest
- E2E: playwright

## Scope Rules
- Do not modify infra or deployment files unless the task explicitly mentions them.
- Do not rename public APIs without approval.
- Do not introduce new libraries unless necessary.

## Done Criteria
A task is complete only if:
1. the requested behavior is implemented or fixed
2. the smallest relevant verification passes
3. changed files are limited to task-relevant scope
4. PROGRESS.md is updated for non-trivial work

## Preferred Workflow
1. read TASKS.md if present
2. inspect relevant files only
3. make minimal patch
4. run verify-fast
5. if needed, run verify-full
6. update PROGRESS.md

## Reporting Format
- Objective
- Root cause
- Files changed
- Commands run
- Result
- Remaining risks