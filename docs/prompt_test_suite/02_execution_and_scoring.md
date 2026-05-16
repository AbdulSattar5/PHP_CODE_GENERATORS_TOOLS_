# Execution and Scoring Guide

Use this with `01_simple_to_complex_prompts.md` to evaluate the project end-to-end.

## Run Order
1. Run prompts 1 to 5 (baseline parser + single-table generation).
2. Run prompts 6 to 10 (relationships + dependencies).
3. Run prompts 11 to 15 (intermediate complexity).
4. Run prompts 16 to 19 (master-detail + stress).
5. Run prompt 20 (negative guardrail check).

## Expected API Outcome
- Prompts 1 to 19: expected success response (`HTTP 200`) with generated code payload.
- Prompt 20: expected strict rejection (`HTTP 422`) with parser/contract error.

## Quick Pass Criteria (per prompt)
- `Parser Contract`: No `SCHEMA PARSING FAILED` for prompts 1 to 19.
- `Generation`: Returns one complete PHP artifact as expected by your flow.
- `Validation`: `approval_status` should be `approved` or at least not hard-failed.
- `Structure`: Table, file name, and title in output match the prompt contract.
- `Fields`: All required fields appear in form/UI and persistence logic.
- `Relationships`: Dropdown fields are present where `-> tblx.Field` is specified.
- `Dependencies`: Pre-delete checks appear where dependencies were requested.
- `Strict Mode`: No fallback output for success cases when strict mode is enabled.

## Deeper Quality Checks
- CRUD completeness: insert, update, delete, list/search behavior all present.
- Security basics: no obvious raw unsafe SQL concatenation in filter paths.
- UX contract: keyboard navigation and validation scripts are present when requested.
- Detail-grid behavior: add/remove line, totals, and row integrity where applicable.
- Session/company pattern compliance: follows your uploaded codebase conventions.

## Suggested Scoring (100 points per prompt)
- 20 points: parser accepted and extracted schema correctly
- 25 points: generated PHP correctness (syntax + runnable structure)
- 20 points: field and relationship fidelity to prompt
- 15 points: dependency and guardrail behavior
- 10 points: validation + keyboard/UX features
- 10 points: style/pattern alignment with company codebase

## Release Readiness Threshold
- Minimum: 17/19 successful positive prompts
- Recommended: 19/19 successful positive prompts
- Mandatory: prompt 20 must fail correctly in strict mode
