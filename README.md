# Mana Pool Daily Reward automation

Checks and (optionally) claims the [Mana Pool](https://manapool.com) **Daily
Reward / Extra Mana** for your account, without a browser. It talks to Mana
Pool's HTTP endpoints directly:

- logs in via the SvelteKit form action `POST /auth?/signin`,
- reads Daily Reward eligibility from `GET /daily/__data.json`,
- reads the Extra Mana balance from Supabase (PostgREST), and
- claims via the SvelteKit form action `POST /daily` when eligible.

No Selenium, Playwright, or headless browser is used.

## Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)

## Setup

```bash
uv sync
cp .env.example .env
# then edit .env with your Mana Pool email + password
```

`.env` (git-ignored) holds your credentials:

```dotenv
MANAPOOL_ACCOUNT_USERNAME=you@example.com
MANAPOOL_ACCOUNT_PASSWORD=your-password
```

Credentials are read only at runtime and are sent only to `manapool.com` /
`sb-api.manapool.com` for authentication.

## Usage

`uv sync` installs the package, exposing the `manapool` console script (you can
also run `uv run python -m manapool`).

Check status and auto-claim when eligible:

```bash
uv run manapool
```

Check status only (never claims):

```bash
uv run manapool --check-only
```

Print diagnostics (endpoint responses and data keys) to stderr:

```bash
uv run manapool --debug
```

Example output:

```text
Mana Pool - Daily Reward status
  Extra Mana available:   16
  Available next month:   1,396
  Eligible (recent order): yes
  Claimed today (UTC):     no
  Time until reset (UTC):  05:53:58

Claiming today's Daily Reward...
Claimed! Awarded 10 Extra Mana.
```

Print the results as a single JSON object on stdout instead of text. Exit
codes are unchanged, and failures are reported as `{"error": "..."}` on stdout:

```bash
uv run manapool --json
```

Combine with `--check-only` to read status without ever claiming:

```bash
uv run manapool --check-only --json
```

Example `--json` output (check-only):

```json
{
  "status": {
    "extra_mana_available": 16,
    "eligible": true,
    "already_claimed": false,
    "seconds_until_reset": 21238,
    "pending_extra_mana": 1396
  },
  "claimed": false,
  "claim": null,
  "status_after": null
}
```

Example `--json` output (eligible, reward claimed):

```json
{
  "status": {
    "extra_mana_available": 16,
    "eligible": true,
    "already_claimed": false,
    "seconds_until_reset": 21238,
    "pending_extra_mana": 1396
  },
  "claimed": true,
  "claim": {
    "award_amount": 10,
    "award_title": "Daily"
  },
  "status_after": {
    "extra_mana_available": 26,
    "eligible": true,
    "already_claimed": true,
    "seconds_until_reset": 21238,
    "pending_extra_mana": 1396
  }
}
```

Example `--json` output (failure):

```json
{
  "error": "Not eligible to claim: no purchase in the last 30 days (or no alternate-entry allowance). See https://manapool.com/daily/rules"
}
```

Fields: `status` is the pre-claim snapshot; `claimed`/`claim` report the claim
outcome (`claim` is `null` when nothing was claimed); `status_after` is a
fresh snapshot taken after a successful claim (`null` otherwise);
`pending_extra_mana` is omitted when the site reports none.

### Docker

The container runs the claim in a loop and publishes the latest result over
HTTP. nginx serves the JSON at `/` (`index.html`) and the same result as
Prometheus text metrics at `/metrics`, on **port 80**, refreshed on container
start and then every day at **01:00 UTC** (files are replaced atomically, so
the server always has a complete copy):

```bash
docker build -t manapool-daily-rewards .
docker run -d -p 80:80 \
  -e MANAPOOL_ACCOUNT_USERNAME \
  -e MANAPOOL_ACCOUNT_PASSWORD \
  manapool-daily-rewards

curl http://localhost/
```

Published images (built by the workflow below):

```bash
docker run -d -p 80:80 \
  -e MANAPOOL_ACCOUNT_USERNAME \
  -e MANAPOOL_ACCOUNT_PASSWORD \
  ghcr.io/findarato/manapool-daily-rewards:latest
```

The refresh time can be overridden with `RUN_AT_UTC` (e.g. `-e RUN_AT_UTC=02:30`).

#### Prometheus metrics

The result is always published as Prometheus text metrics at `/metrics`,
refreshed together with `index.html`:

```bash
docker run -d -p 80:80 \
  -e MANAPOOL_ACCOUNT_USERNAME \
  -e MANAPOOL_ACCOUNT_PASSWORD \
  manapool-daily-rewards

curl http://localhost/metrics
```

```text
# HELP manapool_error 1 when the last run failed, otherwise 0.
# TYPE manapool_error gauge
manapool_error 0
# HELP manapool_eligible 1 when a recent order makes the account eligible.
# TYPE manapool_eligible gauge
manapool_eligible 1
# HELP manapool_already_claimed 1 when today's reward was already claimed before the run.
# TYPE manapool_already_claimed gauge
manapool_already_claimed 0
# HELP manapool_extra_mana_available Extra Mana currently available.
# TYPE manapool_extra_mana_available gauge
manapool_extra_mana_available 16
# HELP manapool_claimed 1 when this run claimed the reward, otherwise 0.
# TYPE manapool_claimed gauge
manapool_claimed 1
```

Exposed series: `manapool_error`, `manapool_eligible`, `manapool_already_claimed`,
`manapool_extra_mana_available`, `manapool_pending_extra_mana`,
`manapool_seconds_until_reset`, `manapool_claimed`, `manapool_claim_award_amount`,
and `manapool_status_after_extra_mana_available` (the last three only when the
value is known). Point a scrape job at the container to collect them:

```yaml
scrape_configs:
  - job_name: manapool
    static_configs:
      - targets: ["manapool:80"]
```

The exporter is a thin conversion over the JSON, available standalone as
`manapool-metrics [payload.json]` (reads stdin when no path is given).

### Scheduled runs (GitHub Actions)

`.github/workflows/daily-reward.yml` builds the container image and publishes
it to the GitHub Container Registry (`ghcr.io/<owner>/<repo>:latest`, plus a
`sha-…` tag) on every push to `main`, on a daily schedule at 01:00 UTC, and
on manual dispatch. The image itself does the daily claiming, so the
credentials are only needed at runtime (`docker run -e ...`), not as
repository secrets.

### Exit codes

Defined as `ExitCode(IntEnum)` in `src/manapool/service.py`:

| Code | Name | Meaning |
| --- | --- | --- |
| 0 | `SUCCESS` | Status reported; reward claimed, already claimed, or check-only |
| 1 | `FAILURE` | Could not read status / claim failed |
| 2 | `AUTH_FAILED` | Missing credentials or sign-in failed |
| 3 | `NOT_ELIGIBLE` | Claim requested but the account is not eligible |

## Project layout

The code is split by domain under `src/manapool/`:

- `cli.py` - argument parsing and the `python -m manapool` entry point.
- `service.py` - the check/claim orchestration (`DailyRewardService`).
- `client.py` - `ManaPoolClient`, the HTTP API surface.
- `transport.py` - the `Transport` protocol and the `requests`-backed implementation.
- `auth/` - SvelteKit sign-in and Supabase session reconstruction.
- `parsing/` - SvelteKit `devalue` decoding and nested-structure search.
- `presentation.py` - pure status formatting, JSON serialization, and Prometheus metrics.
- `exporter.py` - `manapool-metrics`, converting a JSON payload to Prometheus text.
- `config.py`, `console.py`, `models.py`, `errors.py` - settings/credentials, output, domain models, exceptions.

Network access and I/O are injected (`Transport`, `Console`), so the tests run
entirely against fakes with no credentials or network.

## Running tests

```bash
uv run --group dev pytest
```

## How eligibility works

- The reward can be claimed **once per UTC day** and resets at **00:00 UTC**.
- To be eligible you must have **made a purchase in the last 30 days**, or have
  an alternate-entry allowance. See the
  [official rules](https://manapool.com/daily/rules). If you are not eligible,
  the script reports it and exits with code 3 instead of claiming.
- The awarded amount is randomized server-side per Mana Pool's published odds.

## Notes

- This is an unofficial tool that mimics the website's own requests; Mana Pool
  may change its endpoints at any time.
- Run `--debug` if the output looks wrong; it prints the HTTP status and the
  data keys returned by each endpoint (no secret values).
