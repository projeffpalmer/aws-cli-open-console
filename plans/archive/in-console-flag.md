# `--in-console`: open the console page for any AWS CLI command (fork of aws-cli v2)

Ticket: none (no tracker configured). This file is the ticket.
Status: DONE 2026-11-04. Archived with the execution record below. Interface contract: plans/archive/in-console-contract.md

## What we are building

A fork of `aws/aws-cli` (branch `v2`) in which every command accepts `--in-console`.
With the flag, the typed command never runs and no AWS API is called for it. Instead the
CLI resolves the command to the most relevant AWS Management Console page, prints that
URL, and opens it in the browser, signed in with the same credentials the CLI itself would
have used for the command (the CLI's documented credential precedence). Region comes from `--region`, else `AWS_REGION` / `AWS_DEFAULT_REGION`,
else the profile's `region`; profile from `--profile` / `AWS_PROFILE`; partition
(commercial, GovCloud, China) from the region.

With `help` in the command, the flag opens documentation instead: `aws help --in-console`
opens the AWS documentation home, `aws s3 help --in-console` opens the S3 documentation,
`aws s3 ls help --in-console` opens the CLI reference page for `s3 ls`.

Examples: `aws s3 ls --in-console` → S3 buckets list; `aws s3 ls s3://photos/2026/
--in-console` → the `photos` bucket page at prefix `2026/`; `aws lambda get-function
--function-name api --in-console --profile prod` → the `api` function page, via the
prod profile's sign-in.

The first deliverable, before the runtime: a hierarchical database of every CLI command
(tier 0 `aws`, tier 1 service, tier 2 operation, tier 3 `wait` targets) paired with the best
console URL and the best documentation URL for each, generated from the fork's own command
tree and from live console redirects, then hand-curated for the commands people type most.

## Decisions taken at the first gate (2026-11-04)

| # | Decision |
|---|---|
| 1 | A fork of aws-cli, not a plugin |
| 2 | Fork v2 only; v1 is out of scope |
| 3 | Database: nested JSON canonical, CSV for review, YAML overrides for hand edits |
| 4 | Curate all custom commands, the `s3` family and ~65 named services by hand; derive the rest by rules, label confidence |
| 5 | Runtime opens the database URL; the live `go/` resolver only as last-resort fallback |
| 6 | Sign-in aware links in this build ("sso now") |
| 7 | STS calls are allowed when needed to open the console as the right account and role |
| 8 | Always print the URL; open the browser unless print-only (config, env, or headless) |
| 9 | Several ids typed → filtered list page, never multiple tabs |
| 10 | Project name `open-the-console-to-this` |
| 11 | Run straight through; the database lands as its own commit for review |
| A5 | `help` + flag opens documentation, not the console |

## Decisions taken at the second gate (2026-11-04)

| # | Decision |
|---|---|
| 1 | Names: repo `open-the-console-to-this`, module `awscli.customizations.open_the_console_to_this`, data `awscli/data/open_the_console_to_this/`, branch `in-console`; distribution name stays `awscli` |
| 2 | Sign-in integrates with the CLI's credential precedence (AWS doc "Configuration and credential precedence"): whatever credentials the CLI would use for the command are the ones the console is signed in with. No separate SSO shortcut-link path |
| 3 | Federation: long-term keys → `GetFederationToken` with an allow-all inline policy for 1 h; temporary credentials used directly; `SessionDuration` never sent |
| 4 | stdout prints the console destination URL; the sign-in token URL goes only to the browser, or to stdout in print-only mode |
| 5 | Docs targets: docs home / service landing (reference index fallback) / CLI reference page / topic page |
| 6 | Supported install is `pip install` of the fork into a venv; the PyInstaller build is attempted last and may be skipped with a written reason |
| 7 | Sign-in is not configurable: no `in_console_signin` setting, no modes. One fixed behaviour, below |

## Research findings (grounded, 2026-11-04)

Environment: AWS CLI v2 2.39.3 from the official installer (bundled Python 3.14); v2 source
at `v2` branch head (`awscli.__version__ == '2.39.3'`); env credentials are invalid
(`InvalidClientTokenId`) so nothing can be verified signed-in; GovCloud/China hosts blocked.

1. **The fork builds and tests here.** `uv venv` (Python 3.13) + `pip install -r
   requirements-dev-lock.txt` + `pip install -e .` gives a working `aws` that reports
   `source/x86_64`; `tests/unit/test_clidriver.py`, `tests/unit/test_help.py` and
   `tests/functional/configure/test_configure.py` pass (163 tests, 4 s). The build backend
   (`backends/pep517.py`) is flit-based: every file under `awscli/` is packaged, and it
   generates `awscli/data/ac.index` at build time.
2. **Where the flag goes.** Global options are declared in `awscli/data/cli.json`
   (`"debug": {"action": "store_true", "help": "<p>…</p>"}`) and parsed by `MainArgParser`
   with `parse_known_args`, so a `store_true` option is accepted anywhere in argv
   (`aws s3 ls --in-console` and `aws --in-console s3 ls` both work; prototype proved it).
   `CLIDriver.main()` (`awscli/clidriver.py`) parses, calls `_handle_top_level_args`
   (sets profile and region on the session), emits `session-initialized`, then dispatches
   `command_table[parsed_args.command](remaining, parsed_args)`. One `if` before that
   dispatch is the whole hook. Auto-prompt (`AWSCLIEntryPoint`) runs before `main()` and is
   unaffected.
3. **Region/partition inside the CLI**: `session.get_config_variable('region')`;
   `session.get_component('endpoint_resolver').get_partition_for_region(region)`.
4. **The command tree** is walkable in-process exactly as the autocomplete index generator
   does (`awscli/autocomplete/local/indexer.py`: `clidriver.subcommand_table`, then each
   command's `subcommand_table` and `arg_table`, `positional_arg`, `required`, `nargs`).
   2.39.3 counts: tier 0 = 1, tier 1 = 443, tier 2 = 19,618, tier 3 = 412 (`wait` targets).
   Twelve tier-1 commands are custom: `agent-toolkit, cli-dev, configservice, configure,
   ddb, deploy, eventsv2, history, login, logout, s3api, update`; custom subcommands include
   `s3 ls|cp|mv|sync|rm|mb|rb|presign|website`, `logs tail`, `ecr get-login-password`,
   `eks update-kubeconfig`, `ssm start-session`, `cloudformation deploy|package`,
   `configure sso|list|get|set|…`.
5. **Console resolver** (undocumented, answers unauthenticated with a 302 to the current
   page): `go/view?arn=`, `go/view?resourceType=&resourceId=&region=`, `go/list?resourceType=`,
   `go/create?resourceType=`, `go/view?service=`. Snapshots in `research/resolver-snapshots/`:
   services 443 (394 resolve), resource types 1,868 (738 deep list pages, 964 service homes,
   166 none; create 696/987/185), 112 sample ARNs (106 detail pages). `accountId` matters
   only for a few types (CodeBuild).
6. **Documentation URLs.** `https://docs.aws.amazon.com/` (200); CLI reference
   `https://docs.aws.amazon.com/cli/latest/reference/<svc>/<op>.html` and
   `<svc>/<sub>/<op>.html` (200 after redirect, sampled); `<svc>/index.html` for a service.
   The CLI already computes per-command doc URLs for `cli_help_output = url`
   (`awscli/help.py`, `HelpCommand.url`, base `https://awscli.amazonaws.com/v2/documentation/api/<version>`).
   Service landing pages `https://docs.aws.amazon.com/<name>/`: 147 of 443 CLI names exist,
   3 redirect, 46 return 403, 247 return 404 (`research/resolver-snapshots/docs.tsv`), so
   landings need curation plus a reference-index fallback.
7. **Credential precedence.** The CLI resolves credentials in the documented order
   (command line options, environment variables, assume role, assume role with web
   identity, credentials file, custom process, configuration file, container credentials,
   EC2 instance profile; AWS doc "Configuration and credential precedence"). In the fork this
   is `session.get_credentials()`, backed by `create_credential_resolver` in
   `awscli/botocore/credentials.py`, whose providers also include the v2-only `sso` and
   `login` (`aws login`) sources. Every provider yields either temporary credentials
   (access key, secret, session token) or long-term IAM user keys (no token), which is
   the only distinction federation cares about.
8. **Sign-in.** Federation (AWS doc "Enable custom identity broker access"): GET
   `https://signin.aws.amazon.com/federation?Action=getSigninToken&Session=<url-encoded
   {"sessionId","sessionKey","sessionToken"}>` → `{"SigninToken": …}`; then
   `…/federation?Action=login&Issuer=<x>&Destination=<url-encoded>&SigninToken=<t>`; the
   login URL is valid 15 minutes and is a bearer secret. Temporary credentials (assumed
   role, SSO, `aws login`) can be used directly; long-term IAM user keys must first call
   STS `GetFederationToken` (900 s to 129,600 s, needs an inline policy); do not send
   `SessionDuration` with GetFederationToken or role-chained credentials. Partition sign-in
   hosts: `signin.aws.amazon.com`, `signin.amazonaws-us-gov.com`, `signin.amazonaws.cn`.
   Profile SSO settings are read as `BaseSSOCommand._get_sso_config` does
   (`awscli/customizations/sso/utils.py`: `sso_session` section or legacy `sso_start_url`,
   plus `sso_account_id`, `sso_role_name` on the profile). Browser launching from the frozen
   exe must use `open_browser_with_original_ld_path` (same module) or the bundled
   `LD_LIBRARY_PATH` breaks the system browser.
9. **Repo conventions**: changelog entries are JSON files in `.changes/next-release/`
   created by `scripts/new-change`; topic guides live in `awscli/topics/*.rst` with
   `topic-tags.json` regenerated by `scripts/make-topic-index`; functional tests subclass
   `awscli.testutils.BaseAWSCommandParamsTest` (`run_cmd`, `operations_called`, patched
   `make_request` so no request leaves the process); unit tests drive
   `create_clidriver().main([...])`.

## Architecture

```
aws s3 ls s3://photos/2026/ --in-console --profile prod
  MainArgParser → parsed_args.in_console=True, command='s3', remaining=['ls','s3://photos/2026/']
  CLIDriver.main: _handle_top_level_args (profile, region) → session-initialized
    → if parsed_args.in_console: return open_console(session, parsed_args, remaining)
         ├─ 'help' in remaining or command == 'help' → docs URL (no sign-in wrapping)
         ├─ Resolver(db).resolve(command, remaining, ctx) → Decision(url, source, needs_account)
         ├─ creds = session.get_credentials()   # the CLI's own precedence: env, assume-role, sso, login, files, process, container, instance
         ├─ account id if a template needs it: GetFederationToken response ARN → STS GetCallerIdentity (one call, cached)
         ├─ signin.wrap(url, creds): temporary creds → sign-in token; long-term keys → GetFederationToken first; none → plain + warning
         └─ browser.deliver(decision, wrapped): print console URL to stdout; open wrapped URL
```

Upstream files touched (kept minimal so the fork rebases cleanly on upstream `v2`):

| file | change |
|---|---|
| `awscli/data/cli.json` | add the `in-console` global option (`store_true`, `dest: in_console`, help text) |
| `awscli/clidriver.py` | 4 lines in `CLIDriver.main()`: call `open_console` and return its code when the flag is set |
| `awscli/topics/in-console.rst`, `awscli/topics/topic-tags.json` | new topic guide `aws help in-console` |
| `.changes/next-release/feature-in-console-*.json` | changelog entry |
| `tests/unit/test_clidriver.py` | one test for the hook |

New package `awscli/customizations/open_the_console_to_this/` (stdlib + botocore only):

| module | job |
|---|---|
| `__init__.py` | `open_console(session, parsed_args, remaining) -> int` orchestration |
| `db.py` | lazy-loads `awscli/data/open_the_console_to_this/commands.json`; node lookup by path |
| `args.py` | tokenizes remaining args: `--k v`, `--k=v`, repeated/list values, positionals, `help` |
| `resolver.py` | walks tiers 1→2→3, picks intent (list/view/create/home), fills the template, encodes ids, handles several ids → filtered list |
| `urls.py` | partition → console host and sign-in host; regional vs global; placeholders `{host}`, `{region}`, `{id}`, `{account}`, `{bucket}`, `{prefix}`, … |
| `docs.py` | docs home, service landing (DB) with CLI-reference fallback, command reference page, topic page |
| `account.py` | account id from the resolved credentials' identity: the `GetFederationToken` response ARN when that call happens anyway, else STS `GetCallerIdentity`; one call, cached per process; never from profile keys such as `sso_account_id`, which can disagree with higher-precedence credentials |
| `signin.py` | credential resolution through `session.get_credentials()`; federation (`GetFederationToken` for long-term keys, sign-in token exchange via `botocore.httpsession.URLLib3Session` honoring CA bundle and proxies) |
| `browser.py` | stdout gets the console URL; browser gets the wrapped URL via `open_browser_with_original_ld_path`; print-only when `in_console_open = false`, `AWS_IN_CONSOLE_OPEN=false`, no display, or `BROWSER` unset on a headless host |

Config key (profile section, env override): `in_console_open = true | false`
(`AWS_IN_CONSOLE_OPEN`), read through `session.get_scoped_config()`; no clidriver change.
Sign-in has no setting.

Sign-in follows the CLI's credential precedence exactly: `session.get_credentials()`
returns the credentials the typed command would have been signed with (command line
`--profile`, then environment variables, assume role, assume role with web identity, IAM
Identity Center, `aws login`, credentials file, custom process, config file, container,
instance profile). Temporary credentials go straight to the federation endpoint; long-term
IAM user keys are first exchanged with STS `GetFederationToken`. This is the only
behaviour and it is not configurable. When no credentials resolve, the plain deep link is
opened and the CLI's own "Unable to locate credentials" text is printed as a warning on
stderr; a failing STS or sign-in endpoint call also degrades to the plain link with a
warning. Documentation URLs are never wrapped.

Output contract: stdout is exactly one line, the console (or docs) URL. The wrapped sign-in
URL is a 15-minute bearer secret, so it only goes to the browser, or to stdout in
print-only mode (then it is the one line). `--debug` logs the decision (node path, source,
whether sign-in was applied). Exit code 0; failures to open a browser still print and exit 0; resolver
failures cannot happen (every node has a URL) but a broken database file exits 255 with
a clear message.

Resolution chain per command (first hit wins): curated override → resolver-snapshot
detail/list/create page for the command's intent → service home → console home.
Last-resort fallback for a command missing from the database (fork drifted from its
models): `go/list?resourceType=…` or `go/view?service=…` built at runtime.

## Database design

Canonical: `awscli/data/open_the_console_to_this/commands.json` (nested tree, packaged
automatically by flit). Review copies: `scripts/console_db/review/commands.csv` (flat) and
`scripts/console_db/review/STATS.md`. Hand edits: `scripts/console_db/overrides/*.yaml`
(one per service, plus `customs.yaml`, `services.yaml`, `docs.yaml`). Inputs:
`scripts/console_db/snapshots/{services,types,view-samples,docs}.tsv`.

```jsonc
{ "schema": 1,
  "generated": { "awscli": "2.39.3", "snapshot": "2026-11-04", "resource_types": 1868 },
  "root": { "name": "aws", "tier": 0, "kind": "root",
    "url":  { "best": "https://{host}/console/home?region={region}", "source": "curated", "verified": "2026-11-04" },
    "docs": { "best": "https://docs.aws.amazon.com/", "source": "curated" },
    "children": {
      "ec2": { "name": "ec2", "tier": 1, "kind": "service", "title": "Amazon Elastic Compute Cloud",
        "console": { "slug": "ec2", "scope": "regional", "namespaces": ["EC2"] },
        "url":  { "best": "https://{region}.{host}/ec2/home?region={region}", "source": "resolver:service", "verified": "2026-11-04" },
        "docs": { "best": "https://docs.aws.amazon.com/ec2/", "source": "probe", "fallback": "https://docs.aws.amazon.com/cli/latest/reference/ec2/index.html" },
        "children": {
          "describe-instances": { "name": "describe-instances", "tier": 2, "kind": "operation",
            "intent": { "verb": "list", "resource_type": "AWS::EC2::Instance", "id_args": ["--instance-ids"] },
            "url": { "best": "https://{region}.{host}/ec2/home?region={region}#Instances:",
                     "with_id": "https://{region}.{host}/ec2/home?region={region}#InstanceDetails:instanceId={id}",
                     "with_ids": "https://{region}.{host}/ec2/home?region={region}#Instances:instanceId={ids}",
                     "id_encoding": "raw", "source": "resolver:list+view", "verified": "2026-11-04" },
            "docs": { "best": "https://docs.aws.amazon.com/cli/latest/reference/ec2/describe-instances.html", "source": "pattern" } },
          "wait": { "name": "wait", "tier": 2, "kind": "group", "children": {
            "instance-running": { "tier": 3, "kind": "waiter", "intent": { …as describe-instances… }, "url": { … }, "docs": { … } } } } } } } } }
```

Sources, descending confidence: `curated` → `resolver:*` → `derived` → `service-home` →
`console-home`. Docs sources: `curated` → `probe` → `pattern` (reference page) →
`reference-index` fallback.

Generator `scripts/gen-console-db` (package `scripts/console_db/`, deterministic, offline):

1. Walk the fork's command tree in-process (`create_clidriver()`), as the autocomplete
   indexer does, collecting tier, kind, title and arg metadata.
2. Service layer from `services.tsv` + `services.yaml`: slug, scope, home URL,
   CloudFormation namespaces (auto-matched by name; overrides for `logs→Logs`,
   `states/stepfunctions→StepFunctions`, `elbv2→ElasticLoadBalancingV2`,
   `es/opensearch→OpenSearchService`, `kafka→MSK`, `acm→CertificateManager`,
   `cognito-idp→Cognito`, `s3api→S3`, `ddb→DynamoDB`, …). Docs landing from `docs.tsv`
   and `docs.yaml`, fallback to the CLI reference index.
3. Intent per operation: verb from the first word; noun → singular → `AWS::<ns>::<Noun>`
   within the service's namespaces; `id_args` from required args and
   `--<noun>-(name|id|arn|identifier)`, `--name`, `--id`, `--arn`, `--<noun>s`. Record match
   quality.
4. URLs from `types.tsv` (list, create) and `view-samples.tsv` detail shapes with the sample
   id replaced by `{id}`; missing page → fall back a tier. Docs reference URL by pattern.
5. Apply overrides last (a human edit always wins); write JSON, CSV, STATS; run invariants.

Verification: `scripts/verify-console-db` re-requests every distinct host+path (fragment
stripped) unauthenticated and flags non-200/302; `scripts/console_db/review/spot-check.html`
lists every curated URL with sample ids for a signed-in human to click through.

## Phases

### Phase 1: fork and environment
Verified when: the fork exists locally with full `v2` history, the dev venv runs the
upstream tests green, and the plan plus research live inside the fork.
Files to touch: new clone at `/home/user/open-the-console-to-this`; `plans/`,
`scripts/console_db/snapshots/`, `scripts/console_db/README.md`.

#### Step 1.1: clone, branch, dev venv (Size: S)
- Acceptance criteria: `git clone --single-branch --branch v2 https://github.com/aws/aws-cli.git open-the-console-to-this` with full branch history; branch `in-console` created from `v2`; `.venv` via uv (Python 3.13) with `requirements-dev-lock.txt` and `pip install -e .`; `aws --version` reports `source/`; `python -m pytest tests/unit/test_clidriver.py tests/unit/test_help.py` passes.
- Verification command: `.venv/bin/python -m pytest -q tests/unit/test_clidriver.py tests/unit/test_help.py`
- Files likely touched: none in-tree (clone + venv)
- Test seams: upstream unit tests
- Blocked by: none

#### Step 1.2: move plan and evidence into the fork (Size: XS)
- Acceptance criteria: `plans/pending/in-console-flag.md` and `scripts/console_db/snapshots/*.tsv` + README committed on `in-console`; the staging repo `/home/user/aws-in-console` deleted after the move; `.gitignore` covers `.venv/`.
- Verification command: `git -C /home/user/open-the-console-to-this log --oneline -1 && test ! -d /home/user/aws-in-console`
- Files likely touched: `plans/`, `scripts/console_db/snapshots/`, `.gitignore`
- Test seams: none
- Blocked by: 1.1

#### Step 1.3: snapshot tool (Size: S)
- Acceptance criteria: `scripts/snapshot-console-resolver` re-captures any of the four snapshots (network) and `--check --sample 20` compares live redirects with the committed rows.
- Verification command: `.venv/bin/python scripts/snapshot-console-resolver --check --sample 20`
- Files likely touched: `scripts/snapshot-console-resolver`, `scripts/console_db/snapshot.py`
- Test seams: live HTTP (unauthenticated), sampled
- Blocked by: 1.2

### Phase 2: the command database (committed on its own, reviewable any time)
Verified when: every node of the fork's command tree is in `commands.json` with a console
URL and a docs URL, invariants pass, STATS shows the source distribution, and the build is
byte-reproducible.
Files to touch: `scripts/gen-console-db`, `scripts/console_db/*.py`,
`scripts/console_db/overrides/*.yaml`, `awscli/data/open_the_console_to_this/commands.json`,
`scripts/console_db/review/{commands.csv,STATS.md}`,
`tests/unit/customizations/open_the_console_to_this/test_db_invariants.py`.

#### Step 2.1: tree walk and skeleton (Size: S)
- Acceptance criteria: nodes for all tiers with kind ∈ {root, service, operation, custom, group, waiter}; arg metadata attached; counts equal the live command tree (1 / 443 / 19,618 / 412 on 2.39.3).
- Verification command: `.venv/bin/python -m pytest tests/unit/customizations/open_the_console_to_this/test_db_invariants.py -k counts`
- Files likely touched: `scripts/console_db/walk.py`, `scripts/gen-console-db`
- Test seams: unit, against the fork's own command tree (marked `slow`)
- Blocked by: 1.3

#### Step 2.2: service layer and docs landings (Size: S)
- Acceptance criteria: all 443 tier-1 nodes have slug, scope, console home and docs landing; the 49 resolver-unknown names mapped by hand (`ddb→dynamodb`, `s3api→s3`, `deploy→codedeploy`, `pi→rds`, `configservice→config`, `eventsv2→events`, `mturk→requester.mturk.com`, CLI customs and console-less services → console home with `source: console-home`); docs landings curated for the ~65 services of 2.4/2.5, probe-derived for the 147 that exist, reference-index fallback for the rest.
- Verification command: `.venv/bin/python -m pytest tests/unit/customizations/open_the_console_to_this/test_db_invariants.py -k "services or docs"`
- Files likely touched: `scripts/console_db/overrides/{services,docs}.yaml`, `scripts/console_db/services.py`
- Test seams: unit
- Blocked by: 2.1

#### Step 2.3: intent heuristics and snapshot URLs (Size: M)
- Acceptance criteria: ≥ 60 % of tier-2 operations get a resource type match (measured in STATS); every matched type with a list page gets `url.best`; detail templates applied where a `view-samples` shape exists; docs reference URL on every tier-2/3 node; nothing empty.
- Verification command: `.venv/bin/python scripts/gen-console-db && .venv/bin/python -m pytest tests/unit/customizations/open_the_console_to_this/test_heuristics.py`
- Files likely touched: `scripts/console_db/heuristics.py`, `scripts/console_db/urls_from_snapshots.py`, `tests/.../test_heuristics.py`
- Test seams: unit (60 known operation → intent cases)
- Blocked by: 2.2

#### Step 2.4: curated overrides, batch A (Size: M)
- Acceptance criteria: curated entries for every custom tier-1 command and custom subcommand; `s3` (bucket/prefix/object pages, `mb` → create bucket, `website` → properties tab), `s3api`, `ec2` (instances, VPC family, volumes, AMIs, security groups, key pairs, launch wizard), `iam` (users/roles/groups/policies + tabs), `sts`, `lambda` (functions + code/config/monitor/test tabs, layers), `cloudformation` (stack info/events/resources/template/changesets, stacksets, `deploy`, `package`), `logs` (groups, streams, `tail`, Insights), `cloudwatch` (alarms, metrics, dashboards), `dynamodb`/`ddb` (tables, item explorer, PartiQL).
- Verification command: `.venv/bin/python -m pytest tests/unit/customizations/open_the_console_to_this/test_resolver_cases.py -k "customs or s3 or ec2 or iam or lambda or cloudformation or logs or cloudwatch or dynamodb"`
- Files likely touched: `scripts/console_db/overrides/{customs,s3,s3api,ec2,iam,sts,lambda,cloudformation,logs,cloudwatch,dynamodb}.yaml`
- Test seams: unit, table-driven argv → URL (≈ 80 cases written alongside)
- Blocked by: 2.3

#### Step 2.5: curated overrides, batch B (Size: M)
- Acceptance criteria: curated entries for rds, ecs, eks, ecr, sqs, sns, ssm, secretsmanager, kms, apigateway, apigatewayv2, cloudfront, route53, events, scheduler, states, cognito-idp, elbv2, autoscaling, acm, cloudtrail, config/configservice, organizations, ce, budgets, glue, athena, kinesis, firehose, redshift, elasticache, efs, backup, batch, emr, sagemaker, bedrock, bedrock-runtime, codebuild, codepipeline, codecommit, codedeploy/deploy, amplify, appsync, servicequotas, resourcegroupstaggingapi, xray, support, health, sso/sso-admin/identitystore, opensearch, kafka, docdb, neptune (list page, detail page, obvious tab for each service's primary resources).
- Verification command: `.venv/bin/python -m pytest tests/unit/customizations/open_the_console_to_this/test_resolver_cases.py`
- Files likely touched: `scripts/console_db/overrides/<service>.yaml`
- Test seams: unit, table-driven (≈ 120 more cases)
- Blocked by: 2.4

#### Step 2.6: exports, stats, invariants, database commit (Size: S)
- Acceptance criteria: JSON, CSV, STATS regenerate byte-identical; invariants: no empty URL, placeholders ⊆ allowed set, regional templates contain `{region}`, global ones have no region subdomain, every `with_id` has `id_args`, every node has `docs.best`; committed as a single "Add console/docs URL database" commit.
- Verification command: `.venv/bin/python scripts/gen-console-db && git diff --exit-code awscli/data/open_the_console_to_this scripts/console_db/review && .venv/bin/python -m pytest tests/unit/customizations/open_the_console_to_this/test_db_invariants.py`
- Files likely touched: `awscli/data/open_the_console_to_this/commands.json`, `scripts/console_db/review/*`
- Test seams: unit + build determinism
- Blocked by: 2.5

### Phase 3: the flag in the fork
Verified when: on the dev venv, `aws s3 ls --in-console` prints the S3 URL, opens the
capture browser, makes no API call for the command itself; sign-in uses the credentials the
CLI's resolver returns, with stubbed STS and federation endpoints; `aws help --in-console`
opens the docs home.
Files to touch: `awscli/data/cli.json`, `awscli/clidriver.py`,
`awscli/customizations/open_the_console_to_this/*`, tests.

#### Step 3.1: option, hook, docs home (Size: S)
- Acceptance criteria: `--in-console` appears in `aws help` global options; `CLIDriver.main` returns `open_console(...)` when set; `aws help --in-console` prints `https://docs.aws.amazon.com/`; without the flag every existing test still passes; functional test asserts `operations_called == []`.
- Verification command: `.venv/bin/python -m pytest -q tests/unit/test_clidriver.py tests/functional/open_the_console_to_this/test_in_console.py -k "hook or docs_home"`
- Files likely touched: `awscli/data/cli.json`, `awscli/clidriver.py`, `awscli/customizations/open_the_console_to_this/__init__.py`, `tests/functional/open_the_console_to_this/test_in_console.py`
- Test seams: unit (driver), functional (`BaseAWSCommandParamsTest`)
- Blocked by: 2.6

#### Step 3.2: resolver core and docs (Size: M)
- Acceptance criteria: `args.py`, `resolver.py`, `urls.py`, `docs.py` pass the table-driven cases from 2.4/2.5; one id → detail, several → filtered list, none → list; unknown subcommand → service home; `help` at any depth → the matching docs URL; partition hosts for aws / aws-us-gov / aws-cn; ids encoded per template rule.
- Verification command: `.venv/bin/python -m pytest -q tests/unit/customizations/open_the_console_to_this/`
- Files likely touched: `awscli/customizations/open_the_console_to_this/{db,args,resolver,urls,docs}.py`
- Test seams: unit, pure functions
- Blocked by: 3.1

#### Step 3.3: browser delivery and config (Size: S)
- Acceptance criteria: stdout gets exactly the URL line; browser opened through `open_browser_with_original_ld_path`; print-only via `in_console_open`, `AWS_IN_CONSOLE_OPEN`, or headless detection; `--debug` logs the decision; exit 0 even when no browser can open.
- Verification command: `.venv/bin/python -m pytest -q tests/functional/open_the_console_to_this/test_in_console.py -k "stdout or print_only or browser"`
- Files likely touched: `awscli/customizations/open_the_console_to_this/browser.py`
- Test seams: functional with a patched opener
- Blocked by: 3.2

#### Step 3.4: credential resolution (Size: S)
- Acceptance criteria: credentials come only from `session.get_credentials()` (so `--profile`, env vars, assume-role, web identity, SSO, `aws login`, files, process, container and instance-profile sources all work with no special cases); temporary vs long-term detected by the presence of a session token; no credentials → plain link plus the CLI's own credential error text as a warning; functional tests cover an env-var credential set that outranks an SSO profile.
- Verification command: `.venv/bin/python -m pytest -q tests/unit/customizations/open_the_console_to_this/test_signin.py -k resolution`
- Files likely touched: `awscli/customizations/open_the_console_to_this/signin.py`
- Test seams: unit with temp config files (`FileCreator`) and env patches; functional (`BaseAWSCommandParamsTest`)
- Blocked by: 3.3

#### Step 3.5: federation with STS (Size: M)
- Acceptance criteria: temporary credentials → sign-in token exchange → login URL with `Issuer=open-the-console-to-this` and the console destination; long-term keys → STS `GetFederationToken(Name='open-the-console-to-this', Policy=<allow-all inline policy>, DurationSeconds=3600)` first; no `SessionDuration`; partition sign-in hosts; HTTP through `URLLib3Session` honoring `ca_bundle` and proxies; endpoint failures warn and degrade to the plain URL; the login URL is never written to stdout unless print-only.
- Verification command: `.venv/bin/python -m pytest -q tests/unit/customizations/open_the_console_to_this/test_signin.py -k federation tests/functional/open_the_console_to_this/test_in_console.py -k federation`
- Files likely touched: `awscli/customizations/open_the_console_to_this/signin.py`
- Test seams: unit with stubbed `URLLib3Session`; functional with `BaseAWSCommandParamsTest` capturing the `GetFederationToken` call
- Blocked by: 3.4

#### Step 3.6: account id resolution (Size: S)
- Acceptance criteria: `{account}` templates resolve from the `GetFederationToken` response ARN when that call already happened, else one STS `GetCallerIdentity` (cached); never from profile keys; when no credentials resolve the account-less template or list page is used; the STS call never happens for templates that do not need it.
- Verification command: `.venv/bin/python -m pytest -q tests/unit/customizations/open_the_console_to_this/test_account.py tests/functional/open_the_console_to_this/test_in_console.py -k account`
- Files likely touched: `awscli/customizations/open_the_console_to_this/account.py`
- Test seams: unit + functional (`operations_called` shows exactly one `GetCallerIdentity`)
- Blocked by: 3.5

#### Step 3.7: topic guide, changelog, global-option docs (Size: S)
- Acceptance criteria: `aws help in-console` renders the new topic (behaviour, the one config key, sign-in behaviour, limitations); `topic-tags.json` regenerated with `scripts/make-topic-index`; `.changes/next-release/feature-in-console-*.json` created with `scripts/new-change`; `README.rst` gains a short fork section.
- Verification command: `.venv/bin/aws help in-console | head -5 && .venv/bin/python -m pytest -q tests/unit/test_help.py`
- Files likely touched: `awscli/topics/in-console.rst`, `awscli/topics/topic-tags.json`, `.changes/next-release/*.json`, `README.rst`
- Test seams: help rendering
- Blocked by: 3.6

### Phase 4: whole-suite check, packaging, verification
Verified when: the upstream unit and functional suites pass with the fork's changes, a wheel
built from the fork installs into a clean venv and the flag works there, the URL database
re-verifies live, and the spot-check page exists.

#### Step 4.1: full suites (Size: S)
- Acceptance criteria: `tests/unit` and `tests/functional` pass (excluding tests that need network or credentials, as upstream CI does); our tests included.
- Verification command: `.venv/bin/python -m pytest -q -n auto tests/unit tests/functional`
- Files likely touched: fixes only
- Test seams: upstream suites
- Blocked by: 3.7

#### Step 4.2: wheel build and clean install (Size: S)
- Acceptance criteria: `python -m build` (or `pip wheel .`) succeeds using the fork's backend; the wheel contains `awscli/data/open_the_console_to_this/commands.json`; installed into a fresh venv, `aws s3 ls --in-console` prints the URL.
- Verification command: `scripts/ci/… ` not used; `.venv/bin/python -m pip wheel . -w dist --no-deps && unzip -l dist/awscli-*.whl | grep open_the_console_to_this/commands.json`
- Files likely touched: none expected
- Test seams: packaging
- Blocked by: 4.1

#### Step 4.3: self-contained installer build (Size: M, may be skipped)
- Acceptance criteria: `./configure --with-install-type=portable-exe && make && make install` (upstream's PyInstaller path) produces an `aws` that includes the database; if the sandbox cannot build it, record why and leave the venv install as the supported path.
- Verification command: `./build/exe/aws/dist/aws s3 ls --in-console` (path per upstream Makefile)
- Files likely touched: `exe/` only if the data tree is not picked up
- Test seams: the built binary
- Blocked by: 4.2

#### Step 4.4: live verification and spot-check page (Size: S)
- Acceptance criteria: `scripts/verify-console-db` reports no dead host+path among curated and resolver URLs; `scripts/console_db/review/spot-check.html` generated with sample ids; README of `scripts/console_db` explains regeneration after an upstream merge.
- Verification command: `.venv/bin/python scripts/verify-console-db --report scripts/console_db/review/verify-report.md`
- Files likely touched: `scripts/verify-console-db`, `scripts/console_db/spotcheck.py`, `scripts/console_db/review/*`
- Test seams: live HTTP sample; manual click-through by the user
- Blocked by: 4.2

## Decision log

| Decision | Chosen option | Why |
| --- | --- | --- |
| Delivery form | Fork of aws/aws-cli `v2` with the flag built in | user decision (gate 1) |
| v1 | out of scope | user decision (gate 1) |
| Upstream diff size | one option in `cli.json`, a 4-line hook in `clidriver.py`, a topic file, a changelog entry; everything else new files | keeps `git rebase` onto upstream `v2` trivial |
| Hook point | `CLIDriver.main()` after `_handle_top_level_args` and `session-initialized` | profile and region are already applied; both API operations and custom commands pass through this one line |
| Names | repo `open-the-console-to-this`; module `awscli.customizations.open_the_console_to_this`; data `awscli/data/open_the_console_to_this/`; distribution name stays `awscli` | user's name for the project; a renamed distribution would collide with the `awscli` module and the `aws` entry point (gate 2 confirms) |
| Runtime network | none for the typed command; STS and the sign-in endpoints only for sign-in and account id | user decisions 6 and 7 |
| Sign-in identity | the credentials `session.get_credentials()` returns, i.e. the CLI's documented precedence | user decision (gate 2): the console must open as whoever the command would have run as; a profile-level shortcut link could disagree with higher-precedence credentials such as environment variables |
| Sign-in configurability | none: one fixed behaviour, no setting, no env var | user decision (gate 3) |
| No credentials resolve | plain deep link plus the CLI's credential error as a warning on stderr, exit 0 | the deep link is still useful; the warning keeps the failure visible |
| Identity Center shortcut links | not built | superseded by the precedence integration; SSO credentials are temporary role credentials and federate like any other |
| Federation for long-term keys | `GetFederationToken` with an allow-all inline policy, 1 h | effective permissions are the intersection with the user's own; AWS doc requires a policy and long-term keys for this call |
| `SessionDuration` | never sent | fails for GetFederationToken and role-chained credentials; default equals credential lifetime |
| Sign-in URL secrecy | browser only, or stdout in print-only mode | the login URL is a bearer token valid 15 minutes |
| URL source at runtime | database snapshot; `go/` resolver only for commands missing from the database | deterministic and testable; the resolver is undocumented |
| Database format | nested JSON (packaged), CSV + STATS (review), YAML overrides (hand edits) | user decision 3; ruamel.yaml is already a CLI dependency for the build script |
| Command inventory | the fork's own command tree, walked in-process | exactly what this checkout ships; a slow test guards drift after upstream merges |
| `help` semantics | docs home / service docs / CLI reference page / topic page | user's revised assumption 5 |
| Account id | federation response ARN → STS GetCallerIdentity, only when a template needs it; never profile keys | user decision 7; profile keys such as `sso_account_id` can disagree with the credentials that actually won the precedence |
| Several ids | filtered list page (`with_ids`) where the console supports it, else the plain list page (`best`); never the first id's detail page | user decision 9 |
| Intent coverage | 54.2 % of tier-2 operations carry a resource type (60.0 % of the operations whose service has a CloudFormation namespace), below the plan's 60 % figure | measured 2026-11-04: the ceiling under the decided matching rules is 54.3 %; the gap is 1,885 operations of services with no CloudFormation namespace and 775 tag operations; accepted, curation covers the services people use |
| Live URL pass rule | 200, 302 to sign-in, or 302 to the same path on a regional console host | global consoles redirect to `us-east-1.console.aws.amazon.com` (observed for IAM and Route 53) |
| Auto-prompt | unchanged; `--in-console` not added to `_NO_AUTO_PROMPT_ARGS` | the prompter filling required ids makes the URL better, not worse |
| Python floor | 3.9 syntax inside `awscli/` (the fork's `requires-python`) | matches upstream |
| Option abbreviations | `--i`, `--in`, … now resolve to `--in-console` at the top-level parser, as every global option does; accepted, not fixed | approved assumption 2; argparse abbreviation is upstream behaviour and the same thing happens whenever AWS adds a global option (review finding 2026-11-04) |
| Review round | one adversarial round (4 lenses, 19 findings, 11 survived two skeptics, 5 distinct defects: help detection on option values, silent browser failure, multi-line warning, TLS verification with an empty `ca_bundle`, federation credentials in the CLI history database); fixed in one commit; no second round because the fixes are small and test-proven | orchestration rule: a dry or mechanical round does not earn another review |

## Not yet specified

- Phase 4.3: whether the PyInstaller build works in this sandbox (fog; attempted last).
- Phase 2.2: docs landings for services whose `docs.aws.amazon.com/<name>/` is missing are
  curated only for the ~65 named services; everyone else gets the CLI reference index (rule,
  not fog).
- GovCloud / China console and sign-in hosts: derived by partition rule, unverifiable here.
- Console multi-session behaviour when a federated login lands in a browser that already
  has a session (fog; documented as observed once a signed-in user tries it).
- Fragment-level pages (tabs) are unverifiable without login; marked `path-only` until a
  human spot-checks them.

## Always / Never

- Always: zero behaviour change when the flag is absent; never run the typed command when
  it is present; print the console URL; label every URL with its source; keep the upstream
  diff to the files listed above; stdlib + botocore only inside `awscli/`.
- Never: call STS for anything except federation and account id; print a sign-in token URL
  while also opening a browser; open more than one tab; touch autocomplete, auto-prompt or
  pager behaviour; write to `~/.aws/config`.

## Progress

| Phase | Status |
| --- | --- |
| 0 Research + prototype | done (2026-11-04) |
| 1 Fork and environment | done 2026-11-04 (clone 8f11f9f77, branch in-console, venv green on 128 upstream tests; snapshot tool + view-by-id.tsv captured, 1868 types) |
| 2 Command database | done 2026-11-04: 80 override files, 734 curated nodes, 1,055 table-driven cases; all 633 distinct curated and resolver-derived URLs pass the live check (commit 647bc92ef) |
| 3 The flag in the fork | done 2026-11-04 (commits e52630131 sign-in/account, 80fa6e36a option/hook/orchestration/browser + functional tests, 914333d83 docs, 02a996251 parse functions and flag-aware tokenizing) |
| 4 Suites, packaging, verification | done 2026-11-04. 4.1 green: unit+functional 98,967 passed (feature harness 1,626 passed after regeneration); botocore 60,737 passed, 6 failures caused by the sandbox's own ~/.aws/config s3 section (all 6 pass with AWS_CONFIG_FILE=/dev/null); 4.2 wheel built (awscli-2.39.3-py3-none-any.whl, 24.8 MB, carries the database) and proven in a clean venv without credentials; 4.3 PyInstaller installer built with upstream's configure/make in 2.5 min and proven; 4.4 verifier 633/633 pass, spot-check page 734 curated nodes; adversarial review done, five defects fixed (commit after 702de2799) |

## Execution record (2026-11-04)

What shipped, on branch `in-console` of the fork at `/home/user/open-the-console-to-this`
(29 commits on top of upstream `v2` at 8f11f9f77, CLI 2.39.3):

- `--in-console` global option (`awscli/data/cli.json`) and a six-line hook in
  `CLIDriver.main()`; the runtime package `awscli/customizations/open_the_console_to_this/`
  (db, args, params, urls, docs, resolver, account, signin, browser, open_console).
- The database `awscli/data/open_the_console_to_this/commands.json`: 20,474 nodes
  (1 root, 443 tier-1, 19,618 tier-2, 412 tier-3), each with a console URL and a docs URL;
  734 curated nodes across 80 override files; 10,536 operations carry a resource type;
  3,248 generated detail templates. Generator `scripts/gen-console-db`, snapshot tool
  `scripts/snapshot-console-resolver`, validator `scripts/validate-console-overrides`,
  live verifier `scripts/verify-console-db`, spot-check page, review CSV and STATS.
- Sign-in through the CLI's credential precedence (federation; STS GetFederationToken for
  long-term keys), account id from the resolved identity, `in_console_open` print-only
  setting, `help` forms opening documentation, topic guide `aws help in-console`,
  changelog entry, README section, regenerated global-option help pages.

Verification evidence:

- Feature suites: 1,640 unit and functional tests pass; 1,055 table-driven cases pass
  against the regenerated database; generator byte-reproducible.
- Upstream suites: unit + functional without botocore 98,967 passed (the only failures were
  the case harness before regeneration); botocore 60,737 passed, 6 failures caused by the
  sandbox's `~/.aws/config` s3 section (all pass with the config isolated).
- Live URL check: 633 of 633 distinct curated and resolver-derived URLs pass.
- Packaging: wheel `awscli-2.39.3-py3-none-any.whl` (24.8 MB) carries the database and
  works in a clean venv without credentials; the PyInstaller installer builds with
  upstream's `./configure --with-install-type=portable-exe --with-download-deps && make`
  in 2.5 minutes and passes the same checks.
- Adversarial review: 4 lenses, 19 findings, 11 survived two skeptics, 5 distinct defects
  fixed with regression tests (help on option values, silent browser failure, multi-line
  warning, blank `ca_bundle` disabling TLS, federation credentials in `cli_history`).

Deviations from the plan, all recorded in the decision log:

- The resolver core (step 3.2) was built before curation so curated cases could be
  validated in memory; curators never regenerated the database.
- Intent coverage 54.2 % instead of the planned 60 % (measured ceiling under the rules).
- Identity Center shortcut links were dropped in favour of credential-precedence sign-in;
  sign-in is not configurable (user decisions at gates 2 and 3).
- Curation scope grew: 80 services instead of ~65 (dead resolver pages needed homes).
- `ddb` has its own override file; tier-1 names used as file names (`stepfunctions`,
  `configservice`, `deploy`, `service-quotas`).
- Option abbreviations (`--i`, `--in`) now resolve to `--in-console`: accepted.

Known limitations (documented in the topic guide): console pages inside single-page
consoles are verified for host and path only until a signed-in reviewer uses the
spot-check page; GovCloud and China hosts are derived by rule; the `go/` resolver that
the snapshots come from is undocumented; a KMS alias ARN opens the keys page; logs
`--log-group-identifier` ARNs and Organizations policy filters keep their list pages.

Not done: pushing to a remote (no reachable fork and an invalid GitHub token in this
session).
