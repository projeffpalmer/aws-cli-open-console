# Research evidence for the `--in-console` plan

Everything here was captured on 2026-11-04 against the live AWS console, unauthenticated.
The console's `go/` resolver answers with an HTTP 302 whose `Location` is the current
page for a service, resource type, or resource, before any sign-in. That redirect is the
ground truth the command database is built from.

| file | what it is | how it was produced |
|---|---|---|
| `snapshots/services.tsv` | `go/view?service=<cli-name>&region=us-west-2` for all 443 tier-1 CLI command names | one request per tier-1 name from the installed CLI's autocomplete index |
| `snapshots/types.tsv` | `go/list` and `go/create` for all 1868 CloudFormation resource types | type names from the cfn-lint 1.59.0 schema catalog |
| `snapshots/view-samples.tsv` | `go/view?arn=<arn>` for 112 hand-picked ARNs across ~60 services | shows the detail-page URL shape per resource type |
| `snapshots/STATS.md` | coverage summary of `types.tsv` | generated |

Resolver forms observed (all on `https://console.aws.amazon.com`, regional hosts also accepted):

- `go/view?arn=<arn>` → detail page for that resource.
- `go/view?resourceType=AWS::X::Y&resourceId=<id>&region=<r>[&accountId=<a>]` → detail page without needing an ARN. `accountId` only changes the result for a few types (CodeBuild projects fall back to the service home without it).
- `go/list?resourceType=AWS::X::Y&region=<r>` → list page; 404 for unknown types.
- `go/create?resourceType=AWS::X::Y&region=<r>` → create wizard.
- `go/view?service=<slug>&region=<r>` → service home; unknown slugs land on the console home.

The resolver is undocumented by AWS. Third-party write-ups: Matt Fuller (June 2025) and the
`a9s` consolelink package (GET only; HEAD returns 400). Treat it as a build-time source whose
output is snapshotted here, not as a runtime dependency.

Hosts for the GovCloud (`console.amazonaws-us-gov.com`) and China (`console.amazonaws.cn`)
partitions are blocked from this sandbox, so those URLs are derived by partition rule only.

## Documentation landings

`snapshots/docs.tsv` records, for each tier-1 CLI name, whether `https://docs.aws.amazon.com/<name>/`
exists (147 do, 46 answer 403, 247 answer 404) and the status of the CLI reference index
`https://docs.aws.amazon.com/cli/latest/reference/<name>/index.html` (always a redirect to the
live page).

## Detail pages by id, and refreshing the snapshots

`snapshots/view-by-id.tsv` (columns `resource_type, id_status, id_redirect, slash_status,
slash_redirect`) records, for every type in `snapshots/resource-types.txt` (all 1868, not only
those with a list page), the redirect of
`go/view?resourceType=<type>&resourceId=zz9idzz9&region=us-west-2` and of the same request with
`resourceId=zz9%2Fid%2Fzz9`. It shows the detail-page template and how the id is placed in it.
In the 2026-11-04 capture 1727 types answer 302, 138 answer 404 and 3 answer 400 (the same for
both ids); 511 redirects contain the id, and the slash id always comes back decoded as
`zz9/id/zz9`, never as `zz9%2Fid%2Fzz9`.

`snapshots/resource-types.txt` is the sorted list of CloudFormation type names (the first column
of `types.tsv`) that `types` and `view-by-id` probe.

All five snapshots are produced by `scripts/snapshot-console-resolver`
(`scripts/console_db/snapshot.py`, stdlib only, 8 threads, unauthenticated GET without following
redirects, `000` for a host that cannot be reached):

```
.venv/bin/python scripts/snapshot-console-resolver capture view-by-id      # rewrite one or more files
.venv/bin/python scripts/snapshot-console-resolver --check --sample 20 types  # compare every k-th row with live
.venv/bin/python scripts/snapshot-console-resolver --check --sample 20        # all committed snapshots
.venv/bin/python scripts/snapshot-console-resolver --refresh-types            # re-extract resource-types.txt from the latest cfn-lint wheel
```

Names: `services`, `types`, `view-samples`, `view-by-id`, `docs`. `services` and `docs` take the
tier-1 names from `create_clidriver().subcommand_table`; `view-samples` re-probes the ARNs already in
its `input` column. Redirects are stored as curl's `%{redirect_url}` would print them (absolute,
an empty trailing `#` dropped), which matches the first four files (inferred from a row whose raw
Location ends in `#`). `--check` exits 1
when any sampled row differs. Known difference: the log-stream ARN containing `[]` in
`view-samples.tsv` was recorded as 400 because the original capture sent the brackets unencoded;
the tool percent-encodes ARNs and gets a 302 for it.

## Verifying

`scripts/verify-console-db` (`scripts/console_db/verify.py`) renders every `url.best`, `url.with_id`,
`url.with_ids` and `url.variants` template of the database (host `console.aws.amazon.com`, region
`us-west-2`, account `123456789012`, `sample-id` for `{id}`/`{ids}`, curated params from the first
case in `tests/unit/customizations/open_the_console_to_this/cases/<service>.yaml` that gives them,
else `sample`), requests each distinct host+path+query (fragment stripped) once with
`validate.fetch` (8 threads at most, 25 s timeout, two retries on connection errors), classifies it
with `validate.classify_response` (GovCloud and China hosts are SKIP) and writes
`review/verify-report.md`: totals by verdict and by `url.source`, every FAIL with the nodes that use
it, then the SKIP list. It exits 1 only when a URL used by a `curated` or `resolver:*` node fails.
`derived`, `service-home` and `console-home` nodes are service homes already covered by the tier-1
rows, so they are checked only when named in `--sources`.

```
.venv/bin/python scripts/verify-console-db                                  # curated + resolver:*, writes review/verify-report.md
.venv/bin/python scripts/verify-console-db --sources 'curated,resolver:*,derived,service-home,console-home'
.venv/bin/python scripts/verify-console-db --limit 20 --report /tmp/verify.md  # quick re-run on the first 20 URLs
```

Single-page consoles answer an unauthenticated request the same way for good and bad fragments, so
the curated rows also get a human check: `scripts/console_db/spotcheck.py` writes
`review/spot-check.html`, one row per curated node grouped by tier-1 command, with the sample URL
(the first resolver case for the node, else `url.best`) as a link to open in a browser that has a
signed-in console session. Regenerating it belongs to every `scripts/gen-console-db` run:

```
.venv/bin/python scripts/console_db/spotcheck.py                 # [--db PATH] [--out PATH]
```
