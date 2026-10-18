# Security policy

## Reporting a vulnerability

Please report security problems privately through
[GitHub private vulnerability reporting](https://github.com/Ethos6/free-job-search-api/security/advisories/new),
not in public issues. Include steps to reproduce and the version you tested. We aim to reply within a few days.

## Supported versions

Only the latest version on `main` receives security fixes.

## How the API protects you and the sites it reads

- **CVs are not kept.** An uploaded CV is read in a separate, resource-limited process and never written
  to disk, logged, or sent to job sites. Only short search words (roles, skills, place) leave the server.
  If you connect an outside AI service (`JOBS_LLM_URL`), the CV text is sent to that service.
- **Untrusted URLs are checked.** Web pages found by search and alert webhooks must resolve to public
  addresses only, are re-checked on every redirect, and the connection is pinned to the checked address.
  Responses are size-limited.
- **Polite to sources.** An honest User-Agent, per-site pacing, caching, and backing off when a site says no.
  There is no CAPTCHA solving, browser imitation or proxy rotation.
- **Public servers.** Set `JOBS_API_KEYS` to require a key, keep `JOBS_RATE_LIMIT` on, and put the server
  behind HTTPS. Alert links contain a secret token; only a hash of it is stored.

Known limit: anyone who can reach the API can create saved searches up to `JOBS_MAX_ALERTS`; set
`JOBS_API_KEYS` on public servers.
