# HomeNAS API contract

The browser uses the short `/api/*` routes. The read-only aliases under `/api/v1/*` follow the Starter Pack outline so a future Vue client or reverse proxy can migrate without changing collection semantics.

## Browser-facing routes

- `GET /api/health` — public liveness.
- `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me` — local admin session cookie.
- `GET /api/overview` — current snapshot plus five-minute in-memory history.
- `GET /api/system`, `/api/power`, `/api/storage`, `/api/network`, `/api/vpn`, `/api/seafile`, `/api/services`, `/api/alerts` — fixed read-only business views.
- `GET /api/metrics/{metric}` — allowlisted historical metrics only.

## Security

All monitoring routes require the HttpOnly `homenas_session` cookie (Bearer is accepted only for controlled non-browser clients). The browser cannot provide a command, URL, device path or Mihomo Secret. No service-control, arbitrary shell, disk mutation, or configuration-write endpoint exists in this version.

## Unavailable values

Unavailable hardware or external services return `null`, `available: false`, or a quality/reason field. They are never converted to zero or reported as healthy.

