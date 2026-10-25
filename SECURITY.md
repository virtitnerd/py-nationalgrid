# Security policy

## Supported versions

Only the latest release of py-nationalgrid receives security fixes. Please update to the newest version before reporting a problem.

## Reporting a vulnerability

Please do not open a public issue for a security problem.

Report it privately with GitHub's **Report a vulnerability** button on the [Security tab](https://github.com/virtitnerd/py-nationalgrid/security/advisories/new) of this repository. This keeps the details private until a fix is available.

Please include:

- what the problem is and what an attacker could do with it
- the library version and Python version
- steps to reproduce, or a short description of how you found it

Please do not include your National Grid password, tokens, or account numbers in a report. Redact them first.

This project is maintained by one person, so replies are on a best-effort basis. Confirmed vulnerabilities are fixed in a patch release as quickly as practical, and you will be credited in the advisory if you would like to be.

## Scope

In scope: the code in this repository, including how it handles credentials, tokens, authentication, and what it writes to logs and exceptions.

Out of scope: National Grid's own website and services. Please report those to National Grid.

## Dependencies

Dependabot security updates are enabled and `uv.lock` is committed, so a patched dependency version is proposed as soon as an advisory is published. The lockfile only affects development and CI. The version you run is chosen by whoever installs the package.
