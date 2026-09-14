# Security Policy

Blitzcast is a personal portfolio project maintained by Paymon Software.
Response times are best effort, not contractual.

## Supported versions

| Version | Supported |
|---|---|
| Latest release | Yes |
| Anything older | No |

Only the latest release and the current `main` receive security fixes.

## Reporting a vulnerability

Please **do not** open a public GitHub issue for a security vulnerability.
Use GitHub's private vulnerability reporting on this repository:
[github.com/carterptull/blitzcast/security/advisories/new](https://github.com/carterptull/blitzcast/security/advisories/new)

Helpful details: affected component (frontend, API, data pipeline, or
deployment), steps to reproduce, and the impact you believe it has.

## What to expect

- An acknowledgement once the report has been read, typically within a
  few days.
- A follow-up with an assessment and, if the issue is valid, a fix or a
  mitigation plan.
- Coordinated disclosure: please give the fix a chance to ship before
  publishing details. Credit in the advisory is offered if you want it.
- No bug bounty. There is no budget for one on a project like this.

## Scope notes

The app serves read-only sports predictions and stores no user accounts
or personal data. Reports about missing hardening on third-party
services, or about rate limits on free-tier data providers, are welcome
but are likely to be triaged as low priority.

## security.txt

[`/.well-known/security.txt`](https://blitzcast.app/.well-known/security.txt)
([RFC 9116](https://www.rfc-editor.org/rfc/rfc9116)) points researchers at the
private reporting link above. It lives in
`frontend/public/.well-known/security.txt`, and its `Expires` field
(currently 2027-09-14) must be renewed before it lapses: an expired file
tells researchers the contact information is no longer maintained.
