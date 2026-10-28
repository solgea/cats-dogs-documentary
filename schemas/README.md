# JSON schemas

These schemas document the durable JSON contracts used by the pipeline. They are
review aids and integration contracts, not a second implementation of QA. The
authoritative gates live in `src/cddocs/validation.py`, `src/cddocs/batch.py`,
and `src/cddocs/viewmade/adapter.py`.

| Schema | Records |
| --- | --- |
| `package.schema.json` | Editorial source package: scenes, claims, visual policy, YouTube fields, editorial gate |
| `research.schema.json` | Research question, evidence summary, uncertainty, sources, claim checks |
| `batch.schema.json` | Batch manifest and package membership |
| `metadata.schema.json` | Generated manual-upload metadata and disclosure fields |
| `qa-report.schema.json` | Package QA checks, hashes, render state, publication readiness |
| `viewmade-request.schema.json` | Local ViewMade request and honest provider state |
| `viewmade-binding.schema.json` | Explicit render/status/download tool bindings and extraction paths |
| `viewmade-discovery.schema.json` | Sanitised `tools/list` snapshot; no bearer token or session identifier |
| `history.schema.json` | Portable topic-history export committed to git |

## Important distinctions

- `qa-report.json` can say `status: "PASS"` while `publish_ready` is `false`.
  The first value means the checks ran without failures; the second requires a
  validated render and recorded human sign-off.
- `viewmade-request.json` is a local specification. `submission_allowed: false`
  and `status: "NOT_SUBMITTED"` are the safe defaults. Do not change these by
  hand.
- Tool names are discovered at runtime from the official MCP endpoint. They are
  absent from source and configuration until the operator binds them.
- Schemas permit provider additions only where noted. Runtime validators remain
  stricter about evidence domains, subtitle timing, and media structure.

## Validating a record locally

The project intentionally has no third-party runtime dependencies, so schema
validation is advisory. To check syntax with the standard library:

```powershell
python -c "import json,glob; [json.load(open(p, encoding='utf-8')) for p in glob.glob('schemas/*.schema.json')]; print('schemas parse')"
```

If a future tool consumes these schemas, resolve the relative `$id` values as
local catalog names rather than fetching them from the network.
