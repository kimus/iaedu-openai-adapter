---
name: feature-implementation
description: Implements new features in this project. Use when adding or changing app behavior, APIs, utilities, or project structure.
---

# Feature Implementation

## Workflow
1. Inspect the relevant files and understand the existing pattern.
2. Make sure that there are no uncommitted changes about features not about the same implementation.
2. Keep the change small and localized.
3. Prefer updating tests and types together with code.
4. Run lint, typecheck, and tests for the touched area.
5. Update README or AGENTS.md if the workflow changed.

## Conventions
- Use strict code.
- Prefer clear module boundaries.
- Reuse existing helpers before adding new ones.
- Avoid introducing unnecessary dependencies.

## Definition of done
- Code works.
- Tests pass.
- Types pass.
- Formatting and linting pass.
