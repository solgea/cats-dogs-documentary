# ViewMade tool binding

## Why binding is explicit

OAuth gives the pipeline a token. It does not tell the pipeline which MCP tools
exist or how their arguments are shaped. ViewMade may change tool names or input
schemas. Guessing them would create a brittle integration and could send an
invalid or unintended request.

The adapter therefore separates three steps:

1. **Authenticate** with OAuth.
2. **Discover** every tool with the standard MCP `tools/list` method.
3. **Bind** exactly one render, one status, and one download tool, with templates
   validated against the advertised input schema.

Until all three bindings exist, `ViewMadeAdapter.render` raises
`ViewMadeBlocked`. `viewmade-request.json` keeps `submission_allowed: false`.

## Inspect the discovered tools

```powershell
cddocs viewmade status
cddocs viewmade discover
cddocs viewmade tools
cddocs viewmade tools --json
```

`discover` initializes MCP, follows paginated `tools/list` responses, preserves
the server session header, and writes a sanitised snapshot to
`state/viewmade-tools.json`. The snapshot contains tool names, descriptions, and
input/output schemas. It contains no bearer token. It may contain server metadata
and a boolean indicating whether a session id was present, not the session id
itself.

Read the input schema for each candidate before binding. Pay particular attention
to required arguments, nested objects, enum values, and output field names.

## Bind the three operations

```powershell
cddocs viewmade bind `
  --render-tool <exact-name-from-tools-list> `
  --status-tool <exact-name-from-tools-list> `
  --download-tool <exact-name-from-tools-list> `
  --render-template .\state\templates\render.json `
  --status-template .\state\templates\status.json `
  --download-template .\state\templates\download.json
```

The angle-bracket values above are placeholders, not ViewMade tool names. Do not
copy a guessed name from documentation or another account. Use the names printed
by `cddocs viewmade tools` for this authenticated account.

The template files must be JSON objects. Their keys must exist in the tool's
advertised input schema, and every schema-required key must appear. A template
value can be a literal, or an exact placeholder that resolves at call time.

### Supported placeholders

| Placeholder | Resolves to |
| --- | --- |
| `$package_id` | Stable package id, suitable for an idempotency key |
| `$prompt` | Deterministic generation prompt built from the local request |
| `$provider_topic` | Species-specific provider topic, falling back to the title |
| `$script` | Narration split into 7-12 semantic lines |
| `$title` | Package/render title |
| `$duration_s` | Target duration |
| `$aspect_ratio` | `9:16` |
| `$resolution` | `1080x1920` |
| `$narration` | Full narration |
| `$scenes` | Scene array with visual direction |
| `$captions` | Caption object and cues |
| `$disclosure` | Synthetic-media disclosure |
| `$request` | The local request object |
| `$job_id` | Provider job id for status/download |
| `$provider_state` | Last provider state for download |

Placeholders must occupy the entire string value to be substituted. A string
such as `"render $prompt"` is not a supported interpolation; use the provider's
own structure or a template that passes a complete field.

Templates are validated at `tools/call` time for required keys. They are also
checked at bind time against `inputSchema.properties` when the schema exposes
properties. A template key not present in the schema is refused.

## Output extraction

Status and download tools can wrap their useful values differently. Configure
extraction paths rather than editing source:

| Option | Default | Meaning |
| --- | --- | --- |
| `--job-id-path` | `job_id` | Render response path containing the provider job id |
| `--provider-state-path` | `status` | Status response path containing the state string |
| `--success-states` | `complete,completed,succeeded,success,ready,done` | Comma-separated normalized success states |
| `--failure-states` | `failed,error,cancelled,canceled,rejected` | Comma-separated normalized failure states |
| `--download-url-path` | `url` | Download response path containing an HTTPS URL |
| `--download-file-path` | `path` | Download response path containing a local file |

Paths use dot notation (`data.job.id`) or a JSON array argument
(`["data","job","id"]`) when a key itself contains a dot. If the configured path
is absent, the adapter has a small fallback list such as `job_id`, `id`,
`render_id`, `video_id` for a job id and `url`, `download_url`, `video_url` for a
download URL. Fallbacks are a recovery aid, not permission to guess success.

## Binding record

The resulting `state/viewmade-binding.json` records:

- the exact render/status/download tool names;
- each argument template;
- job id and provider state paths;
- success and failure state vocabularies;
- download URL/file paths.

It is local operational state and is gitignored. Inspect it before the first live
render. If ViewMade changes a schema, re-run `discover`, re-check the tools, and
bind again. Do not edit a binding to add a made-up tool name.

## Refusal cases

Binding fails when:

- no discovery snapshot exists;
- a requested tool is not in the discovered list;
- a template is not a JSON object;
- a required input-schema argument is missing;
- a template key is not in the advertised input schema;
- a placeholder is unknown;
- a template cannot resolve a value at call time.

These are intentional hard stops. A binding is permission to call three specific
provider operations — not permission to publish a video.
