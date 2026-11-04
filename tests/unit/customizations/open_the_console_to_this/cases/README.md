# Resolver cases

Each `<service>.yaml` here is a list of cases; `test_resolver_cases.py` runs every case through `resolve()` against the committed database, and `scripts/validate-console-overrides` runs them against the database with the override files applied.
Required keys: `argv` (the tokens after `aws`, e.g. `[s3, ls, "s3://photos/2026/"]`) and `url` (the exact expected console URL).
Optional keys: `source` (expected `url.source`, e.g. `curated`), `region` (default `us-west-2`), `partition` (default `aws`) and `account` (quoted string; default: no account id available).
Unknown keys fail the load; every curated node needs at least one case in the file named after its tier-1 command.
Use only sample ids from `scripts/console_db/snapshots/`, never real identifiers.
