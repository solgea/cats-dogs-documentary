# Topic deduplication

## Purpose

The channel should not publish the same explanation twice under a new title. The
history system catches exact reuse, very similar framing, and repeated use of the
same primary source. It is intentionally simple and auditable rather than a
black-box embedding model.

## Storage model

- `state/history.db` — local SQLite database. It is machine state and gitignored.
- `state/history.json` — committed export for review and cross-machine history.
- `content/batches/<batch-id>/batch.json` — package membership for one batch.

A successful `batch build` registers each package topic only if the aggregate
batch status is not `FAIL`. A `batch validate` checks existing artifacts but does
not register new topics. The export is written after the batch build.

Do not resolve history conflicts by copying SQLite files between machines.
Review the JSON export, reconcile the intentional topic list, and rebuild the
local database through the normal registration path.

## Scoring

Both title and combined topic text are normalized to lowercase ASCII words,
stopwords are removed, and token Jaccard similarity is calculated. Combined text
uses title + central question + central fact.

For a candidate against history:

| Condition | Severity | Reason |
| --- | --- | --- |
| Candidate slug already exists | `FAIL` | Slug already used |
| Same package id in another batch | `FAIL` | Package id already belongs to another batch |
| Title similarity ≥ 0.86 | `FAIL` | Near-identical title |
| Combined similarity ≥ 0.66 | `FAIL` | Topic framing too similar |
| Combined similarity ≥ 0.45 | `WARN` | Overlapping framing; review before publishing |
| Same primary source as an earlier topic | `WARN` | Same source reused, even if text is different |

Rebuilding the same package in the same batch is idempotent and does not match
itself. A candidate id moving to another batch is always a failure; choose a new
slug/id for a genuinely new package.

Within a batch, every pair is scored at 0.66/0.45. A failing pair is added to
both packages' QA reports. A warning pair is allowed through packaging but remains
visible.

The scoring is lexical. It cannot understand synonymy or conceptual duplication
perfectly. Use it as a tripwire, then apply editorial judgement: two videos can
share a broad subject and still ask genuinely different questions.

## Workflow for a new batch

1. Draft each candidate's title, central question, and central fact before
   writing the full package.
2. Check each candidate with `cddocs history check <slug>` once the package files
   exist.
3. Change the angle, question, or source if the check returns `FAIL`. Do not
   merely reword a title to lower the score.
4. Review any `WARN` explicitly. Same-source reuse may be legitimate if it asks a
   different question, but it needs a documented reason.
5. Build the batch. Inspect `duplicate_pairs` in the aggregate report and the
   `history.dedup` check in each package.
6. Commit the updated `state/history.json` with the batch.

## Commands

```powershell
cddocs history list
cddocs history list --json
cddocs history check dog-guilty-look
cddocs history check dog-guilty-look --json
cddocs history export
```

`history check` reads the package and research records and reports candidate
matches without registering the topic. The build is the registration point.

## Current batch

`2026-10-29-cats-dogs-01` contains six distinct questions:

- dog guilty-look interpretation;
- cat sweet-taste pseudogene;
- dog inner-eyebrow muscle;
- cat response to a human slow blink;
- solicitation purr acoustics;
- dog nasal airflow.

At the configured thresholds, there are no failing or warning pair matches. That
is a lexical check, not a claim that the topics are scientifically unrelated; it
means their titles and central framings are sufficiently distinct for this
batch's editorial review.
