:title: AWS CLI Console Pages
:description: Using the --console-link and --open-console options to open the AWS Management Console page for a command
:category: General
:related command: sts get-federation-token, sts get-caller-identity, configure set
:related topic: config-vars

The ``--console-link`` global option opens the AWS Management Console page that
best matches a command, instead of running the command. Add it to any
command::

    $ aws s3 ls s3://photos/2026/ --region us-west-2 --console-link
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
AWS STS ``GetCallerIdentity`` call when the chosen page needs your account ID
or the type of your temporary credentials has to be checked, and one request
to the AWS federation endpoint. Opening a documentation page
with ``help`` (see `Help and Documentation`_) makes no network calls and does
not read your credentials. In print-only mode (see
`Printing the URL Without Opening a Browser`_) nothing is signed in, so the
only possible call is ``GetCallerIdentity`` for a page that needs your
account ID.

Messages, such as a sign-in warning, are written to standard error. Standard
output only ever holds the one URL, so the output can be used in scripts::

    $ url=$(aws lambda get-function --function-name my-function --console-link)


How the Page Is Chosen
======================

The AWS CLI builds the console URL when you run the command. For each
command the first match wins:

* A page for the resource named on the command line, for services whose
  console address is known: Amazon S3, Amazon EC2, AWS Lambda, Amazon
  DynamoDB, AWS IAM, Amazon CloudWatch Logs, AWS CloudFormation and
  Amazon SQS. For example,
  ``aws ec2 describe-instances --instance-ids i-0123456789abcdef0`` opens
  that instance, and ``aws s3 ls s3://photos/2026/`` opens that prefix of
  the bucket. One resource id opens that resource. Several ids open the
  list.
* An ARN in the arguments opens AWS's console resolver,
  ``/go/view?arn=``. ``--open-console`` also uses an ARN from the API
  response when the command does not already name a page above.
* The home page of a service whose console address is known, when the
  command names no resource.
* ``/go/view?service=`` for any other service name.
* The console home page for a CLI-only command such as ``configure``.

The page is chosen from the command line (and, for ``--open-console``,
from the API response). It does not check that the named resource exists,
or that you have permission to see it.


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
configured or turned off: it takes place whenever the console is opened in
a browser. In print-only mode (see
`Printing the URL Without Opening a Browser`_) no browser is opened, so
nothing is signed in.

* **Temporary credentials** (credentials with a session token, such as those
  from IAM Identity Center, assume role or ``aws login``) are exchanged
  directly at the AWS federation endpoint for a sign-in token. The console
  only accepts role sessions and federated user sessions, so unless the
  credentials come from IAM Identity Center, assume role, web identity, the
  container provider or the instance profile, one AWS STS
  ``GetCallerIdentity`` call checks the identity first. Temporary
  credentials of an IAM user or the root user, such as those from
  ``aws login`` or ``sts get-session-token``, cannot be used to sign in;
  the console is opened without signing in, with a warning. A browser that
  ``aws login`` used is usually still signed in to the console.
* **Long-term IAM user access keys** are first exchanged with AWS STS
  ``GetFederationToken`` for one hour of temporary credentials. The request
  uses the federated user name ``open-the-console-to-this`` and an inline
  policy that allows all actions on all resources. An inline policy can only
  restrict permissions, never add them, so the console session has no more
  permissions than the IAM user. The IAM user needs permission to call
  ``sts:GetFederationToken``.

The sign-in URL opened in the browser is a bearer secret that is valid for 15
minutes. It is given to the browser and to nothing else: it is never printed
and never logged, including with ``--debug``. Only the console URL is
printed. Where a message has to quote the sign-in URL, such as the warning
when the browser cannot open it, the sign-in token in it is replaced by
``sha256:`` and the first 16 hexadecimal digits of the token's SHA-256 hash,
which cannot be used to sign in.

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

In print-only mode the printed line is the console URL, the same line as
when a browser is opened. Nothing is signed in and no sign-in URL is made,
because a sign-in URL is only ever given to a browser. The console asks you
to sign in when you open the printed URL, unless that browser is already
signed in.

``in_console_open`` is the only setting for this option.


Opening the Console After a Command Runs
========================================

The ``--open-console`` global option runs the command exactly as it runs
without the option, and also opens the console page of the resource the
command acted on::

    $ aws dynamodb create-table --table-name MusicCollection ... --open-console

The table is created and the AWS CLI output is the same as without the
option. After the command completes, the browser opens the
``MusicCollection`` table page, signed in as described in `Signing In`_,
where the table's status (``Creating``, then ``Active``) is shown.

The resource is found in the command's API response, and in the typed
arguments when the response does not name it:

* ``aws ec2 run-instances ... --open-console`` opens the launched instance.
  When several instances are launched, the instances list page is opened.
* ``aws lambda create-function --function-name api ... --open-console``
  opens the ``api`` function.
* ``aws s3 mb s3://photos --open-console`` opens the ``photos`` bucket.

The page is that of the command itself when it shows one resource, otherwise
that of the command that describes the same kind of resource, such as
``describe-table`` for ``create-table``. When the command names no resource,
the page that ``--console-link`` would open for the command is used.

Differences from ``--console-link``:

* The command always runs. Nothing is opened when it fails.
* Standard output is the command's own output. The console URL is not
  printed. In print-only mode (see
  `Printing the URL Without Opening a Browser`_) the console URL is written
  to standard error instead, and nothing is signed in.
* ``help`` only shows help.
* With both options, ``--console-link`` wins and the command does not run.

An error while choosing the page or signing in never changes the command's
output or exit code; it is reported on standard error, for example
``Could not open the console (<reason>).``. A paginated command fetches
every page before its output is displayed.


Help and Documentation
======================

With ``help``, ``--console-link`` opens the documentation instead of the
console. Documentation pages are never signed in and no credentials are read.

* ``aws help --console-link`` opens the AWS documentation home page,
  ``https://docs.aws.amazon.com/``.
* ``aws s3 help --console-link`` opens the documentation landing page of the
  service, or its AWS CLI reference when the service has no landing page.
* ``aws s3 ls help --console-link`` opens the AWS CLI reference page of the
  command.
* ``aws help <topic> --console-link`` opens the online version of a topic
  guide, such as this one with ``aws help in-console --console-link``.
  ``aws help topics --console-link`` opens the topic index.


Limitations
===========

* Most console URLs are not documented by AWS and can change when a console
  is redesigned. A page that has moved can show an error or the service
  home page instead.
* Many consoles are single-page applications whose pages are addressed after
  a ``#`` in the URL.
* The AWS GovCloud (US) and China console and sign-in hosts are chosen from
  the partition of the region.
* A service without a built-in page opens through ``/go/view``. That follows
  an ARN when the command has one, and otherwise opens the service by name.
