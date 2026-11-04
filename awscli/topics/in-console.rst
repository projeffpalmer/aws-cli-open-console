:title: AWS CLI Console Pages
:description: Using the --in-console option to open the AWS Management Console page for a command
:category: General
:related command: sts get-federation-token, sts get-caller-identity, configure set
:related topic: config-vars

The ``--in-console`` global option opens the AWS Management Console page that
best matches a command, instead of running the command. Add it to any
command::

    $ aws s3 ls s3://photos/2026/ --region us-west-2 --in-console
    https://console.aws.amazon.com/s3/buckets/photos?region=us-west-2&prefix=2026%2F&showversions=false

The AWS CLI prints the console URL as one line on standard output and opens it
in your web browser, signed in with the credentials the command would have
used. The exit code is ``0``, including when no browser could be opened.

This option is part of the open-the-console-to-this fork of the AWS CLI; it is
not available in the AWS CLI distributed by AWS.


What the Option Does and Does Not Do
====================================

The typed command never runs. Its API operation is not called, nothing is
created, changed or deleted, and the command's arguments are not validated
against the service. The command line is only used to choose a console page.

The only network calls are those needed to sign in to the console (see
`Signing In`_): at most one AWS STS ``GetFederationToken`` call, at most one
AWS STS ``GetCallerIdentity`` call when the chosen page needs your account ID,
and one request to the AWS federation endpoint. Opening a documentation page
with ``help`` (see `Help and Documentation`_) makes no network calls and does
not read your credentials.

Messages, such as a sign-in warning, are written to standard error. Standard
output only ever holds the one URL, so the output can be used in scripts::

    $ url=$(aws lambda get-function --function-name my-function --in-console)

If the console URL database that ships with the AWS CLI cannot be read, the
AWS CLI writes ``Unable to load the console URL database: <path>: <error>``
to standard error and exits with ``255``.


How the Page Is Chosen
======================

The AWS CLI includes a database of console pages with one entry for every
command of this version of the AWS CLI. For each command the first match
wins:

* A curated page for that command. Common services, such as Amazon S3,
  Amazon EC2, AWS Lambda, Amazon DynamoDB, AWS IAM, Amazon CloudWatch Logs and
  AWS CloudFormation, have hand-checked pages, including detail pages that use
  the resource name or ID given on the command line. For example,
  ``aws ec2 describe-instances --instance-ids i-0123456789abcdef0`` opens that
  instance, and ``aws s3 ls s3://photos/2026/`` opens that prefix of the
  bucket.
* A list, detail or create page for the kind of resource the command works
  on, recorded from the console's own resource resolver.
* The home page of the service in the console.
* The console home page.

When a command has several resource IDs, a list page is opened where the
console supports one. When the database has no entry for a command (for
example, a command added by a plugin), the console's service page for the
command name is opened.

The database records the console page for a command. It does not check that
the named resource exists, or that you have permission to see it.


Region and Profile
==================

The region and profile are resolved the same way as for any other command:

* The profile comes from ``--profile``, then the ``AWS_PROFILE`` environment
  variable, then the ``default`` profile.
* The region comes from ``--region``, then the ``AWS_REGION`` or
  ``AWS_DEFAULT_REGION`` environment variable, then the ``region`` setting of
  the profile. When no region is configured, ``us-east-1`` is used.

The region also selects the partition, and with it the console and sign-in
hosts: ``console.aws.amazon.com`` for the standard partition,
``console.amazonaws-us-gov.com`` for AWS GovCloud (US) regions and
``console.amazonaws.cn`` for the China regions. An unknown region uses the
standard partition.


Signing In
==========

The browser is signed in to the console with the credentials the command
would have been signed with. They are resolved with the AWS CLI's normal
credential precedence: the profile given with ``--profile``, environment
variables, assume role, assume role with web identity, IAM Identity Center,
``aws login``, the shared credentials file, a credential process, the config
file, the container provider and the instance profile. Sign-in cannot be
configured or turned off.

* **Temporary credentials** (credentials with a session token, such as those
  from IAM Identity Center, assume role or ``aws login``) are exchanged
  directly at the AWS federation endpoint for a sign-in token.
* **Long-term IAM user access keys** are first exchanged with AWS STS
  ``GetFederationToken`` for one hour of temporary credentials. The request
  uses the federated user name ``open-the-console-to-this`` and an inline
  policy that allows all actions on all resources. An inline policy can only
  restrict permissions, never add them, so the console session has no more
  permissions than the IAM user. The IAM user needs permission to call
  ``sts:GetFederationToken``.

The sign-in URL opened in the browser is a bearer secret that is valid for 15
minutes. It is never printed in normal mode and never logged, including with
``--debug``. Only the console URL is printed.

When no credentials can be found, the console is opened without signing in
and the following warning is written to standard error::

    Unable to locate credentials. Opening the console without signing in.

When a credential provider fails, the warning is the provider's error message
followed by ``Opening the console without signing in.`` When the AWS STS call
or the federation endpoint fails, the warning is::

    Console sign-in failed (<reason>). Opening the console without signing in.

In each case the plain console URL is still printed and opened, and the exit
code is ``0``. The console then asks you to sign in.

The AWS CLI uses your ``ca_bundle`` setting and the ``HTTPS_PROXY`` and
``NO_PROXY`` environment variables for the request to the federation
endpoint, as it does for API calls.


Printing the URL Without Opening a Browser
==========================================

The AWS CLI only prints the URL, and does not open a browser, when any of the
following applies:

* The ``AWS_IN_CONSOLE_OPEN`` environment variable is ``false``.
* The ``in_console_open`` setting of the profile is ``false``.
* The AWS CLI runs on Linux or BSD without a ``DISPLAY`` or
  ``WAYLAND_DISPLAY`` environment variable, such as over SSH or in a
  container.

The values ``false``, ``0``, ``no`` and ``off`` are accepted, in any case.
Any other value, or no value, keeps the browser behaviour; a ``true`` value
in one place does not override a ``false`` value in the other. For example::

    [profile build-server]
    region = us-west-2
    in_console_open = false

In print-only mode the printed line is the URL to open: the sign-in URL when
sign-in succeeded, otherwise the console URL. Paste it into a browser within
15 minutes. Because it is a bearer secret, do not store it or share it.

``in_console_open`` is the only setting for this option.


Help and Documentation
======================

With ``help``, ``--in-console`` opens the documentation instead of the
console. Documentation pages are never signed in and no credentials are read.

* ``aws help --in-console`` opens the AWS documentation home page,
  ``https://docs.aws.amazon.com/``.
* ``aws s3 help --in-console`` opens the documentation landing page of the
  service, or its AWS CLI reference when the service has no landing page.
* ``aws s3 ls help --in-console`` opens the AWS CLI reference page of the
  command.
* ``aws help <topic> --in-console`` opens the online version of a topic
  guide, such as this one with ``aws help in-console --in-console``.
  ``aws help topics --in-console`` opens the topic index.


Limitations
===========

* Most console URLs are not documented by AWS and can change when a console
  is redesigned. A page that has moved can show an error or the service
  home page instead.
* Many consoles are single-page applications whose pages are addressed after
  a ``#`` in the URL. Those pages cannot be checked without signing in, so
  some detail pages in the database were recorded from the console's
  resource resolver and were not opened in a signed-in console.
* The AWS GovCloud (US) and China console and sign-in hosts are derived by
  rule from the standard partition's URLs and were not checked against those
  partitions.
* The database matches this version of the AWS CLI. A command added to the
  AWS CLI later, or by a plugin, falls back to the service page of its command
  name.


Regenerating the Console Database
=================================

The database is ``awscli/data/open_the_console_to_this/commands.json``. It
is generated, and should not be edited by hand. In a checkout of the fork,
the scripts under ``scripts/`` rebuild it:

* ``scripts/snapshot-console-resolver`` records what the console's resource
  resolver answers, into ``scripts/console_db/snapshots/``. Use
  ``capture NAME...`` to record a snapshot again and
  ``--check --sample 20`` to compare the recorded snapshots with the live
  console. It needs network access.
* Curated pages are YAML files under ``scripts/console_db/overrides/``, one
  per service, with test cases under
  ``tests/unit/customizations/open_the_console_to_this/cases/``.
* ``scripts/validate-console-overrides`` runs those cases against the
  database with the overrides applied. ``--service NAME`` runs one service
  and ``--check-urls`` also requests every expected URL.
* ``scripts/gen-console-db`` walks the command tree of the checkout,
  combines it with the snapshots and the overrides, and writes the database
  plus a review file and statistics under ``scripts/console_db/review/``. The
  same inputs always produce the same output.

For example::

    $ python scripts/validate-console-overrides --service s3
    $ python scripts/gen-console-db
