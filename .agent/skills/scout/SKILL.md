# Northstar Research Skill

Use this skill when generating or revising Northstar market intelligence artifacts for a startup concept.

## Purpose

This skill standardizes the research pipeline that powers:

- Research Mode
- Advisory Board follow-ups that depend on research context
- War Room scenarios that depend on verified competitor evidence

It exists to keep source-backed facts, modeled assumptions, and generated strategy clearly separated.

## When To Use It

Use this skill when all of the following are true:

- The user wants startup research, market mapping, competitor analysis, or market sizing.
- The output should become a reusable artifact that other Northstar views can load.
- The workflow needs citation discipline, numeric sanity checks, and schema-shaped output.

Do not use this skill for:

- Generic chat that does not need a saved research artifact
- Authentication or user-account workflows
- UI-only changes with no effect on research generation

## Required Inputs

Collect or confirm these fields before generation:

- `startup_concept`
- `geography`
- `sector`
- `funding_scale`

If one or more are missing, ask for them before running the full workflow.

## Core Workflow

1. Capture the startup concept and context fields.
2. Research competitors, pricing, positioning, and market signals.
3. Preserve source URLs for every material claim that can be cited.
4. Compute market-sizing scaffolding with the helper formula script.
5. Audit URLs, structure, and numeric fields before finalizing.
6. Write a hybrid Markdown artifact with schema-compatible structured fields.
7. Reuse that artifact for downstream Advisory Board and War Room steps.

## Backend Selection

- Prefer Google ADK when the ADK package and required environment variables are available.
- Fall back to the local pipeline when ADK is unavailable or a step fails cleanly.
- Keep the artifact contract stable across both execution paths.

## Source Discipline

- Separate direct evidence from model inference.
- Keep citations attached to factual claims, competitor records, and pricing references.
- Do not present modeled estimates as if they were directly sourced.
- If web retrieval is weak or ambiguous, reduce confidence and say so explicitly.
- Prefer partial but defensible output over invented detail.

## Numeric Discipline

- Keep numeric fields numeric in the structured artifact.
- Use explicit units when rendering prose, such as monthly price or annual revenue.
- Avoid copying a single default price across all competitors unless the source evidence truly supports it.
- If competitor pricing is missing, mark the gap and avoid overconfident TAM math.

## Helper Assets

Use the local skill assets instead of re-implementing their logic:

- `scripts/verify_links.py`
  - Verifies URLs with `HEAD` and `GET` fallback.
  - Use it to flag dead links, redirects, and non-HTML targets.
- `scripts/fetch_tam_formula.py`
  - Computes `monthly_price`, `annual_price`, `tam`, `sam`, and `som`.
  - Default pricing fallback exists, but sourced pricing should be preferred whenever available.
- `scripts/evidence_normalizer.py`
  - Cleans snippets, removes obvious noise, and ranks evidence excerpts.
- `scripts/pricing_normalizer.py`
  - Extracts monthly pricing, infers pricing visibility, and standardizes fallback price bands.
- `scripts/artifact_qa.py`
  - Performs a final saved-artifact QA summary before output is written.
- `schemas/market_schema.yaml`
  - Defines the minimum structured contract for project name, brief, competitors, and market sizing.

## Expected Output Contract

The final artifact should contain:

- project identity and startup brief
- competitor table or list with names, URLs, and pricing where available
- market sizing section with assumptions and bottom-up figures
- citations grouped so evidence is distinct from assumptions
- enough structured fields to satisfy `schemas/market_schema.yaml`

Minimum structured fields:

- `project_name`
- `brief.concept`
- `brief.geography`
- `brief.sector`
- `brief.funding_scale`
- `competitors[].name`
- `competitors[].source_url`
- `market_sizing.assumptions.monthly_price`
- `market_sizing.assumptions.annual_price`
- `market_sizing.assumptions.n_global_customers`
- `market_sizing.assumptions.n_target_customers`
- `market_sizing.assumptions.capture_rate`
- `market_sizing.bottom_up.tam`
- `market_sizing.bottom_up.sam`
- `market_sizing.bottom_up.som`

## Failure Handling

If auditing fails:

- revise the draft instead of returning a broken artifact
- remove or downgrade unsupported claims
- re-run link checks for suspect URLs
- keep the prior valid artifact intact until a replacement passes

If search coverage is thin:

- return fewer competitors rather than hallucinating more
- mark missing pricing or missing evidence explicitly
- preserve the research trace so the user can see what happened

If the selected backend is unavailable:

- log the reason
- continue with the local fallback path when possible

## Quality Bar

A good run should satisfy all of these:

- links resolve or are clearly flagged
- competitor names are specific and non-duplicative
- prices are sourced or clearly marked unknown
- TAM, SAM, and SOM assumptions are inspectable
- evidence and inference are visually distinct
- downstream tabs can reuse the saved artifact without losing state

## Example Invocation Shape

Example user input:

- startup concept: `A subscription service for automated indoor vertical farming using IoT sensors`
- geography: `United States`
- sector: `AgTech`
- funding scale: `Seed stage, bootstrapped pilot`

Expected behavior:

- gather competitors and market evidence
- compute sizing using observed or best-available pricing inputs
- audit links and numeric fields
- save a reusable artifact for Research, Advisory Board, and War Room

## Guardrails

- Never fabricate citations.
- Never collapse evidence and inference into one unlabeled section.
- Never discard a valid prior artifact unless a new one replaces it successfully.
- Never block the whole workflow just because one citation or one price is missing.
