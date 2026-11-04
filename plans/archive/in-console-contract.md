# Interface contract: `--in-console` (open-the-console-to-this)

Companion to `plans/pending/in-console-flag.md`. Every worker builds against this file.
When this file and the plan disagree, this file wins for interfaces; the plan wins for
scope. If something here is impossible or contradicts the code you read, STOP and report
it in your summary instead of working around it.

## 0. Ground rules for every worker

- Repository: `/home/user/open-the-console-to-this`, a fork of `aws/aws-cli` branch `v2`,
  feature branch `in-console`. Work only inside this directory. Never run `git commit`,
  `git add`, `git checkout` or any history-changing command; the orchestrator commits.
- Interpreter and tools: `.venv/bin/python` (Python 3.13, editable install of this
  checkout). Run tests with `.venv/bin/python -m pytest -q -p no:cacheprovider <paths>`.
  Lint with `.venv/bin/ruff check <paths>` and `.venv/bin/ruff format --check <paths>`
  (repo config: line length 79, rules E4/E7/E9/F/I/UP). If `ruff` is missing from the
  venv, say so in the report; do not install anything into the venv.
- Code under `awscli/` is Python 3.9 compatible (the fork's `requires-python`): no
  `match`, no `X | Y` in runtime annotations, no `list[str]` annotations without
  `from __future__ import annotations`, stdlib + `botocore` only (the fork vendors it;
  import it as `botocore` like the rest of `awscli` does). Start new files with the same
  Apache-2.0 header block the upstream files use.
- Zero behaviour change when `--in-console` is absent. Do not touch upstream files other
  than those the plan lists for your step.
- Unit tests make no network calls. Functional tests subclass
  `awscli.testutils.BaseAWSCommandParamsTest` (`run_cmd` returns `(stdout, stderr, rc)`;
  `self.operations_called` lists every API call as `(OperationModel, params)`;
  `make_request` is patched so nothing leaves the process).
- Report format (mandatory, at the end of your final message): pass/fail per check you
  ran with the exact command; a concise summary; `git diff --stat`-style list of files
  you created or changed; then one line each for "Skipped or could not run", "Deviated
  from the brief and why", "Risks". Do not end on "done".

## 1. The database: `awscli/data/open_the_console_to_this/commands.json`

Schema version 1. A single JSON object, compact (`separators=(',', ':')`, `sort_keys=True`,
UTF-8, no indentation), written only by `scripts/gen-console-db`.

```jsonc
{
  "schema": 1,
  "generated": {"awscli": "2.39.3", "snapshot": "2026-11-04", "resource_types": 1868},
  "root": <Node>
}
```

`Node` fields (absent means null/not applicable; `children` absent on leaves):

| field | type | meaning |
|---|---|---|
| `name` | str | the token the user types (`ec2`, `describe-instances`, `instance-running`) |
| `path` | str | dotted path from the root: `aws`, `aws.ec2`, `aws.ec2.describe-instances`, `aws.ec2.wait.instance-running` |
| `tier` | int | 0 root, 1 service or custom top-level, 2 operation/custom subcommand/group, 3 waiter |
| `kind` | str | `root`, `service`, `custom` (tier-1 non-service such as `configure`), `operation` (API operation), `subcommand` (custom subcommand such as `s3 ls`), `group` (such as `ec2 wait`), `waiter` |
| `title` | str or null | service full name from the model, or the custom command description |
| `console` | object or null | services only: `{"slug": str, "scope": "regional" or "global" or "special", "namespaces": [str]}`; `slug` is the first path segment of the console URL (`ec2`, `sqs`, `states`); `special` means a host that is not `console.aws.amazon.com` (`lightsail.aws.amazon.com`, `quicksight.aws.amazon.com`, `support.console.aws.amazon.com`, `health.console.aws.amazon.com`, `resource-explorer.console.aws.amazon.com`), kept literal |
| `positional` | [str] | names of positional CLI args in order (`["paths"]` for `s3 ls`, `["outfile"]` for `lambda invoke`; custom commands and the 61 API operations with a streaming output file) |
| `flags` | [str] | only on nodes that have positional args: option names (without `--`) that take no value (`recursive`, `human-readable`), so the tokenizer never swallows a positional typed after a flag |
| `scalars` | [str] | only on nodes that have positional args: option names (without `--`) that take exactly one value, so a positional typed after `--function-name f` is not read as a second value |
| `intent` | object or null | `{"verb": "home" or "list" or "view" or "create", "resource_type": str or null, "id_args": [str], "params": {name: ParamSpec}}`; `id_args` are CLI option names with the leading `--` (`"--instance-ids"`); `params` is curated only (section 1.2) |
| `url` | object | see 1.1 |
| `docs` | object | `{"best": str, "source": "curated" or "probe" or "pattern" or "reference-index", "fallback": str or null}` |
| `children` | {name: Node} | child nodes keyed by `name` |

### 1.1 `url` object and the template language

```jsonc
"url": {
  "best": "https://{region}.{host}/ec2/home?region={region}#Instances:",
  "with_id": "https://{region}.{host}/ec2/home?region={region}#InstanceDetails:instanceId={id:raw}",
  "with_ids": "https://{region}.{host}/ec2/home?region={region}#Instances:instanceId={ids:raw}",
  "variants": [ {"when": ["bucket", "prefix"], "template": "..."}, {"when": ["bucket"], "template": "..."} ],
  "needs_account": false,
  "source": "resolver:list+view",
  "verified": "2026-11-04",
  "note": null
}
```

- `best`: always present; the page to open when no identifier was typed.
- `with_id` / `with_ids`: optional; generated entries use them with the first value /
  all values of the first present `id_args` option. `with_ids` is used only when two or
  more values were typed and it exists; otherwise fall back to `best`.
- `variants`: optional, curated only; evaluated in order; the first whose `when` names
  are all present in the resolved params wins; otherwise `best`.
- `needs_account`: true when any template of this node contains `{account}`.
- `source`: `curated`, `resolver:service`, `resolver:list`, `resolver:list+view`,
  `resolver:create`, `derived`, `service-home`, `console-home`.
- `verified`: ISO date of a live unauthenticated check of host+path (fragment stripped),
  `"path-only"` when only the path could be checked and the fragment is unverified,
  or null.

Placeholders are `{name}` or `{name:enc}` with `enc` one of:

| enc | meaning |
|---|---|
| `path` (default when omitted) | `urllib.parse.quote(value, safe='')` |
| `query` | `urllib.parse.quote_plus(value, safe='')` |
| `raw` | inserted as typed |

Encoding rule for generated `with_id` / `with_ids` templates (verified 2026-11-04: the
resolver decodes slashes in every one of its 511 id-bearing redirects, so the encoding
cannot be read off the snapshot): `{id:raw}` when the id option name ends in `arn` or
`arns` (every console observed places ARNs raw in fragments); `{id:query}` when the
sentinel sits in a query parameter value (`?x=zz9idzz9` or `&x=zz9idzz9` before any `#`;
53 types); otherwise `{id}` (path encoding). Curated overrides fix the consoles that want
something else (CloudWatch Logs wants `%2F`, which path encoding produces; Systems
Manager parameter paths are curated).

Built-in placeholder names: `{host}` partition console host (`console.aws.amazon.com`,
`console.amazonaws-us-gov.com`, `console.amazonaws.cn`), `{region}`, `{id}`, `{ids}`
(comma-joined, each value encoded individually), `{account}`. Curated templates may use
any additional name declared in `intent.params`. Regional URLs use the
`https://{region}.{host}/...` host form; global ones `https://{host}/...`; `special`
hosts are literal.

### 1.2 Curated params (`intent.params`)

```jsonc
"params": {
  "bucket": {"arg": "paths", "parse": "s3uri_bucket"},
  "prefix": {"arg": "paths", "parse": "s3uri_prefix"}
}
```

`arg` is a CLI option name with `--` or a positional name. `parse` is one of the
functions below; every function receives the full list of values typed for that arg
(a positional with `nargs` 2 gives both values) and returns a string or null (null means
"param absent"). Default `parse` is `first`.

| parse | behaviour |
|---|---|
| `first` | first value |
| `last` | last value |
| `s3uri_bucket` | bucket of the first S3 URI among the values; accepts `s3://b/k`, `b/k`, `b` |
| `s3uri_key` | key of that URI (text after the bucket and `/`), or null when empty |
| `s3uri_prefix` | key up to and including the last `/`; null when the key has no `/` |
| `s3uri_object` | key when it does not end with `/`; null otherwise |
| `s3_target_bucket` / `s3_target_key` / `s3_target_prefix` | for `cp`/`mv`/`sync`: use the last value when it is an S3 URI, else the first; then as the `s3uri_*` functions |
| `arn_resource` | the ARN's resource part after the service/region/account fields, with a leading `resource-type/` or `resource-type:` removed when present |
| `arn_account` / `arn_region` | the ARN's account id / region |
| `queue_url_name` / `queue_url_account` | last / second-to-last path segment of an SQS queue URL |
| `basename` | text after the last `/` |
| `present` | `"1"` when the option was typed (even as a bare flag), null when absent; the only function that accepts an empty value list |
| `is_arn` | the value itself when it looks like `arn:partition:service:...`, else null (use as a presence gate in `when`) |
| `arn_type` | the resource type of an ARN (`key` in `arn:aws:kms:...:key/uuid`, `alias` for `alias/name`), null when the ARN has no type |
| `arn_name` | the last `/`- or `:`-separated segment of an ARN's resource (`MyRole` for `role/service-role/MyRole`) |
| `before_colon` / `after_colon` | text before / after the first `:` |
| `before_dot` | text before the first `.` |
| `first_label` | first DNS label of a hostname |
| `lower` | lower-cased value |
| `strip_leading_slash` | value without one leading `/` |
| `ensure_trailing_slash` | value with a `/` appended when it has none |
| `strip_wildcard_suffix` | value without a trailing `:*` |
| `secret_name` | a Secrets Manager secret name from an ARN (drops the trailing `-xxxxxx` suffix) or a plain name unchanged |
| `s3uri_dir` | the key treated as a folder: the key with a `/` appended when it has none (`logs` → `logs/`) |
| `prefix_dir` | a plain prefix value cut to its last `/` inclusive (`photos/2026` → `photos/`) |
| `s3_target_object` | the target key when it does not end with `/`, else null |
| `filters_first_value` | the first `Values=` entry of an EC2-style `--filters Name=x,Values=a,b` value |

## 2. Override files: `scripts/console_db/overrides/*.yaml`

Loaded with `ruamel.yaml` (already a CLI dependency; build time only). Top-level keys are
node paths. Each value may set `intent`, `url`, `docs`, `title`; it replaces those objects
on the node entirely (no deep merge), so repeat `source: curated` and `verified` in every
override. Unknown paths fail the build with a message naming the key.

```yaml
# scripts/console_db/overrides/s3.yaml
aws.s3.ls:
  intent:
    verb: list
    resource_type: AWS::S3::Bucket
    id_args: []
    params:
      bucket: {arg: paths, parse: s3uri_bucket}
      prefix: {arg: paths, parse: s3uri_prefix}
  url:
    best: "https://{host}/s3/buckets?region={region}"
    variants:
      - when: [bucket, prefix]
        template: "https://{host}/s3/buckets/{bucket}?region={region}&prefix={prefix}&showversions=false"
      - when: [bucket]
        template: "https://{host}/s3/buckets/{bucket}?region={region}"
    source: curated
    verified: path-only
    note: bucket page; the prefix parameter opens the folder view
```

Override conventions learned from the s3 pilot (2026-11-04): quote `verified` dates
(`"2026-11-04"`, an unquoted date loads as a date object); `needs_account` may be
omitted (the generator recomputes it at export); `resource_type: null` is fine when no
CloudFormation type exists (S3 objects); transfers such as `s3 cp` use verb `view`;
YAML anchors and aliases are welcome for repeated templates; a path appears in exactly
one override file, custom subcommands of a service (`logs tail`, `eks update-kubeconfig`)
live in that service's file, and the eight custom tier-1 commands (`configure`, `history`,
`cli-dev`, `update`, `agent-toolkit`, `login`, `logout`) in `customs.yaml`; `ddb` is a
tier-1 name of its own and lives in `ddb.yaml` (decided 2026-11-04 after the curation
wave). Tier-1 CLI names are the file names: `stepfunctions` (not `states`), `configservice`
(not `config`), `deploy` (not `codedeploy`), `service-quotas` (not `servicequotas`). A curated tier-1 node needs its case in the service's
own case file, and the tier-1-only `cases/services.yaml` must not keep a conflicting row.
Parse functions receive only options that carry values: a bare flag such as `--recursive`
cannot be a param yet, so cases put flags after positionals and do not depend on flags.
Path encoding (`{prefix}`) matches the resolver, which returns `%20` for spaces and `%2F`
for slashes.

`services.yaml` keys are tier-1 names: `{slug, scope, home, namespaces, title}`.
`docs.yaml` keys are tier-1 names: `{landing}`. `customs.yaml` holds the twelve custom
tier-1 commands and their subcommands.

## 3. Generator: `scripts/console_db/` (build time only, not packaged)

| module | signature |
|---|---|
| `walk.py` | `walk_command_tree(driver) -> dict` root node with `name/path/tier/kind/title/positional/children`, plus a private `_args` map per node (`{cli_name: {"required": bool, "list": bool, "positional": bool}}`) that is removed before export |
| `services.py` | `apply_service_layer(root, services_tsv_rows, overrides) -> None` fills `console`, service `url`, service `docs` |
| `heuristics.py` | `derive_intent(node, service_node, resource_types) -> (intent, quality)` with quality in `exact`, `fuzzy`, `none`; verb rules and noun matching per the plan |
| `urls_from_snapshots.py` | `assign_urls(root, snapshots) -> None` using `types.tsv` (list, create), `view-by-id.tsv` (detail), `services.tsv` (home); templating rule: replace the probe host/region with `{region}.{host}` or `{host}`, `region=us-west-2` with `region={region}`, and the sentinel `zz9idzz9` with `{id}` using the encoding rule of section 1.1; a `view-by-id` row whose `id_redirect` does not contain the sentinel, or whose status is not 302, means the type has no detail page (fall back to the list page) |
| `docs.py` | `assign_docs(root, docs_tsv_rows, overrides) -> None`: root → `https://docs.aws.amazon.com/`; service → landing when the probe says 200/301 or a curated landing exists, else `https://docs.aws.amazon.com/cli/latest/reference/<name>/index.html`; tier 2/3 → `https://docs.aws.amazon.com/cli/latest/reference/<svc>/<op>.html` or `<svc>/<group>/<op>.html` |
| `overrides.py` | `load_overrides(dir) -> dict`, `apply_overrides(root, overrides) -> None` |
| `export.py` | `write_json(root, meta, path)`, `write_csv(root, path)` (columns: path, tier, kind, verb, resource_type, id_args, url_best, url_with_id, url_source, url_verified, docs_best, docs_source), `write_stats(root, path)` |
| `snapshot.py` | capture and `--check` for `services`, `types`, `view-samples`, `view-by-id`, `docs` |
| `verify.py` | re-request every distinct host+path, write a report |
| `spotcheck.py` | render `review/spot-check.html` |

Scripts: `scripts/gen-console-db`, `scripts/snapshot-console-resolver`,
`scripts/verify-console-db`, each a small executable Python file in the style of
`scripts/gen-ac-index` that adds `scripts/` to `sys.path` and calls the package.
Review outputs go to `scripts/console_db/review/`.

The generator must be deterministic: same inputs → byte-identical outputs (sorted keys,
sorted children, no timestamps except the committed `snapshot` date passed on the
command line).

## 4. Runtime: `awscli/customizations/open_the_console_to_this/`

```python
# __init__.py
def open_console(session, parsed_args, remaining):  # -> int exit code
```
Called from `CLIDriver.main()` after `_handle_top_level_args` and `_emit_session_event`,
before dispatch. `parsed_args.command` is the tier-1 token; `remaining` is the rest of
argv as a list.

```python
# db.py
DB_PATH: str                                   # awscli/data/open_the_console_to_this/commands.json
def load_db():                                 # -> dict, cached in a module global
def find_node(root, tokens):                   # -> (node, consumed, rest): walk children by
                                               #    consecutive tokens; stop at the first token that is
                                               #    not a child name or starts with '-'

# args.py
class ParsedArgs:                              # .options: {name_without_dashes: [values]}, .positionals: [str], .help: bool
def parse_remaining(tokens, positional_names): # -> ParsedArgs; '--k v1 v2' collects until the next token
                                               #    starting with '--'; '--k=v' supported; a bare '--k' is a flag ([]);
                                               #    'help' anywhere among positionals sets .help

# urls.py
def partition_for_region(session, region):     # -> 'aws' | 'aws-us-gov' | 'aws-cn' (unknown region -> 'aws')
def console_host(partition):                   # -> host string per section 1.1
def signin_host(partition):                    # -> 'signin.aws.amazon.com' | 'signin.amazonaws-us-gov.com' | 'signin.amazonaws.cn'
def render(template, params):                  # -> str; implements {name} / {name:enc}; missing name -> KeyError
def console_home(host, region):                # -> 'https://{host}/console/home?region={region}' rendered

# docs.py
DOCS_HOME = 'https://docs.aws.amazon.com/'
def docs_url(root, node, tokens_after_node):   # -> str; 'aws help' -> DOCS_HOME; 'aws help <topic>' ->
                                               #    'https://docs.aws.amazon.com/cli/latest/topic/<topic>.html';
                                               #    otherwise node['docs']['best']

# resolver.py
class Context:  region: str; partition: str; account_id: callable returning str or None (called lazily)
class Decision: url: str; node_path: str; source: str; verb: str; params: dict; explanation: str
def resolve(root, command, remaining, ctx):    # -> Decision; never raises for user input
# resolution: find_node -> parse_remaining -> params from intent (id_args, params, parse functions)
# -> pick template: variants (curated) > with_ids (>=2 ids) > with_id (1 id) > best
# -> render with host/region/account; unknown subcommand tokens -> the deepest matched node's best page;
# -> last resort for a missing node: 'https://{host}/go/view?service=<command>&region=<region>'

# account.py
class AccountResolver:                          # __init__(session, region)
    def set_from_arn(self, arn): ...            # remember an account id seen in a federation response
    def get(self): ...                          # -> str or None; one STS GetCallerIdentity call, cached; errors -> None

# signin.py
ISSUER = 'open-the-console-to-this'
FEDERATION_POLICY = '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":"*","Resource":"*"}]}'
def resolve_credentials(session):              # -> (frozen_credentials or None, warning or None); uses session.get_credentials()
def federation_login_url(session, creds, destination, partition, region, account_resolver):
                                               # long-term keys (no token) -> STS GetFederationToken(Name=ISSUER,
                                               #    Policy=FEDERATION_POLICY, DurationSeconds=3600) first;
                                               # GET https://<signin_host>/federation?Action=getSigninToken&Session=<quote_plus(json)>
                                               #    via botocore.httpsession.URLLib3Session (verify from the session's
                                               #    ca_bundle setting, proxies from the environment); no SessionDuration;
                                               # -> 'https://<signin_host>/federation?Action=login&Issuer=<ISSUER>&Destination=<quote_plus>&SigninToken=<token>'
def wrap(session, destination, partition, region, account_resolver):
                                               # -> (url_to_open, warning or None): no credentials -> (destination, warning)

# browser.py
def print_only(session):                       # -> bool: in_console_open config false / AWS_IN_CONSOLE_OPEN false
                                               #    / Linux or BSD without DISPLAY and WAYLAND_DISPLAY
def deliver(console_url, open_url, session):   # -> 0; stdout gets exactly one line: console_url, or open_url when
                                               #    print-only; opens open_url with
                                               #    webbrowser.open_new_tab inside sso.utils.original_ld_library_path()
                                               #    unless print-only; a False result or an exception -> warning on stderr, still 0
```

Behaviour contract for `open_console`:

1. If `parsed_args.command == 'help'` or `help` appears among the positionals: compute the
   docs URL, print it, open it, return 0. No sign-in wrapping, no credentials touched.
2. Region: `session.get_config_variable('region')`; when None use `us-east-1` and log at
   debug level. Partition from the region.
3. `decision = resolve(...)`. If the database cannot be loaded, write
   `Unable to load the console URL database: <path>: <error>` to stderr and return 255.
4. `account_resolver = AccountResolver(session, region)`; it is only called when a
   template needs `{account}` (`url.needs_account`) or by `federation_login_url` when it
   already received an ARN.
5. `open_url, warning = signin.wrap(...)`. A warning is written to stderr, prefixed with
   nothing (plain text), one line.
6. `return browser.deliver(decision.url, open_url, session)`.
7. `--debug` logging via `logging.getLogger(__name__)`: node path, source, verb, params,
   whether sign-in was applied, which credential method
   (`credentials.method`) was used. Never log secrets or the sign-in URL.

Warnings text (exact): no credentials → `Unable to locate credentials. Opening the console
without signing in.`; credential provider error → `<exception message>. Opening the
console without signing in.`; federation endpoint failure → `Console sign-in failed
(<reason>). Opening the console without signing in.`

## 5. Tests

- Unit: `tests/unit/customizations/open_the_console_to_this/test_<module>.py`, plain
  `unittest`/pytest in the upstream style, no network, no credentials.
- Resolver cases: `tests/unit/customizations/open_the_console_to_this/cases/<service>.yaml`,
  loaded by `test_resolver_cases.py` (one parametrized test per case). Case format:

```yaml
- argv: [s3, ls, "s3://photos/2026/"]
  url: "https://console.aws.amazon.com/s3/buckets/photos?region=us-west-2&prefix=2026%2F&showversions=false"
  source: curated
- argv: [ec2, describe-instances, --instance-ids, i-0123456789abcdef0]
  url: "https://us-west-2.console.aws.amazon.com/ec2/home?region=us-west-2#InstanceDetails:instanceId=i-0123456789abcdef0"
  region: us-west-2            # default us-west-2
  partition: aws               # default aws
  account: "123456789012"      # default: no account available
```

- Functional: `tests/functional/open_the_console_to_this/test_in_console.py` using
  `BaseAWSCommandParamsTest`; patch `awscli.customizations.open_the_console_to_this.browser.open_browser_with_original_ld_path`
  and the sign-in HTTP call (`signin._http_get`) so nothing leaves the process. Note the
  harness exports long-term fake keys in `self.environ`, so the default path produces one
  `GetFederationToken` call in `operations_called`; set `AWS_SESSION_TOKEN` for the
  temporary-credentials path and clear the key variables (plus empty config files) for the
  no-credentials path, which must show `operations_called == []`.
- Database invariants: `test_db_invariants.py` loads the committed JSON and checks every
  node: non-empty `url.best`, placeholders ⊆ allowed set, regional templates contain
  `{region}`, global ones have no region subdomain, `with_id` implies `id_args` or
  `params`, `docs.best` present, tier/path consistency, and (marked `slow`) that the set
  of node paths equals the live command tree of this checkout.

## 6. Curation rules (steps 2.4 and 2.5)

1. The best page for a command is the page where a console user would perform that
   command's job: list operations → the resource list; get/describe/update/delete with an
   id → that resource's page, on the tab that shows what the command returns when the tab
   is known; create → the create wizard when the resolver has one, else the list.
2. Evidence before invention. Take templates from, in order: the snapshot files, a live
   probe of the resolver (`curl -sS -o /dev/null -w '%{redirect_url}' 'https://console.aws.amazon.com/go/view?resourceType=...&resourceId=...&region=us-west-2'`),
   the reference projects under
   `/tmp/claude-0/-home-user/12d4a421-b5e3-55f1-ba89-9fe76bad2e4e/scratchpad/src/`
   (`link2aws.github.io/link2aws.js`, `granted/pkg/console/service_map.go`,
   `arn-to-url/awsurl/awsurl.go`), or an AWS documentation page that shows the URL.
   A template with no evidence is not written; the node keeps its generated entry.
3. Every curated template is checked live for host+path (fragment stripped): a 200, a
   302 whose Location contains `signin`, or a 302 to the same path on another console
   host of the same partition (global consoles redirect `console.aws.amazon.com/<path>`
   to `us-east-1.console.aws.amazon.com/<path>`) is a pass; a `go/` fallback URL passes
   when its 302 lands on a console host; anything else is a fail and the entry is dropped.
   Record `verified: <date>` when the whole URL was observed from the resolver, or
   `verified: path-only` when only the path could be checked. Caveat: single-page-app
   consoles (S3 among them) answer 200 for any path, so a path-only pass proves the host
   and prefix, not the page; tabs and fragments are proven only by the resolver or by a
   signed-in spot check.
4. Each curated node gets at least one case in the matching `cases/<service>.yaml`.
5. Never put account ids, bucket names or other real identifiers from this machine into
   templates or cases; use the sample ids from the snapshots.
