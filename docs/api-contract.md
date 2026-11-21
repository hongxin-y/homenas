# HomeNAS API contract

The browser uses the short `/api/*` routes. The read-only aliases under `/api/v1/*` follow the Starter Pack outline so a future Vue client or reverse proxy can migrate without changing collection semantics.

## Browser-facing routes

- `GET /api/health` — public liveness.
- `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me` — local admin session cookie.
- `GET /api/overview` — current snapshot plus five-minute in-memory history.
- `GET /api/system`, `/api/power`, `/api/storage`, `/api/network`, `/api/vpn`, `/api/seafile`, `/api/services`, `/api/alerts` — fixed read-only business views.
- `GET /api/v1/power/daily` — local-calendar-day valid perf/RAPL energy totals in J, Wh and kWh.
- `POST /api/vpn/ping` — authenticated, bounded one-host ICMP probe; accepts only an IP address or hostname and never invokes a shell.
- `GET /api/metrics/{metric}` — allowlisted historical metrics only.

## Security

All monitoring routes require the HttpOnly `homenas_session` cookie (Bearer is accepted only for controlled non-browser clients). The browser cannot provide a command, URL, device path or Mihomo Secret. Mihomo reads use fixed server-side endpoints (`/version`, `/configs`, `/rules`, `/proxies`); opt-in node/rule operations are fixed Controller calls, and persistent rule editing can only send a validated rules array to the reviewed local config path or restricted root helper socket. Perf RAPL is a long-lived server-side subprocess; its stderr is parsed and only valid intervals are stored. There is no service-control or arbitrary shell endpoint.

## Unavailable values

Unavailable hardware or external services return `null`, `available: false`, or a quality/reason field. They are never converted to zero or reported as healthy.

