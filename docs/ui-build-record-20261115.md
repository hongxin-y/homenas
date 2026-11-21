# HomeNAS UI / Mihomo build record

## Execution ledger

| Step | Artifact / decision | Status |
| --- | --- | --- |
| 0. Scope and facts | USER: repair frontend continuity and make Mihomo editable. REPO: static TypeScript UI, FastAPI plus standalone backend, server-side Mihomo Controller env. EVIDENCE: `main.ts` re-rendered the page every 5 seconds; mutations were gated and rule drafts were validation-only. ASSUMPTION: persistent editing is limited to the top-level `rules` list. | DONE |
| 1. Task model | Actor is the authenticated local administrator. Objects are Mihomo proxy groups, selected nodes, loaded rules and the reviewed config file. Node selection changes live traffic; rule apply writes config and reloads Mihomo. | DONE |
| 2. Route model | VPN entry → inspect Controller state → choose group/node → confirm switch → refresh state. Rules entry → edit → validate → explicit confirm → backup/atomic write/reload → success or automatic rollback. | DONE |
| 3. Page scope / blueprint | VPN remains the canonical owner for node selection, runtime rule toggles, rule editing and ping. Draft and node selection persist across collector refreshes. Mobile keeps controls inside the panel and permits horizontal table scrolling only when content requires it. | DONE |
| 4. Art direction | Inherited the existing daylight operations desk contract: paper canvas, terracotta action, semantic status colors, compact data density. No new visual language introduced. | DONE |
| 5. Spatial orchestration | Sidebar is its own vertical scroll owner; content clips horizontal overflow at the page boundary; tables own horizontal scrolling; mobile sheet locks body scroll and returns focus to its trigger. | DONE |
| 6. Layout / interaction | VPN uses a monitoring workbench with inline actions. Node switch is explicit; rule persistence is a separate confirm action. Draft validation stays reversible and does not write. | DONE |
| 7. Cost / continuity | Removed the 5-second draft loss: textarea input and selected nodes are held in client state. Navigation no longer uses smooth scrolling during route changes. | DONE |
| 8. Visual system | Added shared button row and focus/overflow repairs without changing the established palette. Disabled writeback is labeled with the exact server-side reason. | DONE |
| 9. UI engineering blueprint | Added explicit scroll owners, `min-width:0` paths, focus-safe panel overflow, sheet scroll lock, and stable mobile controls. | DONE |
| 10. Review / repair | Static/type/runtime checks rerun. The local Chrome snapshot at 1440px and mobile 390/360px showed no document horizontal overflow for the reachable shell. Full Mihomo fixture data and authenticated NAS browser session were not available in this workstation audit. | DONE with limitation |
| 11. Delivery | Frontend build, backend guarded writeback path, tests, deployment configuration and activation/rollback notes delivered. | DONE |

## Mihomo mutation boundary

- `HOMENAS_ENABLE_MIHOMO_MUTATIONS=1` enables node selection and runtime rule toggles.
- `HOMENAS_MIHOMO_CONFIG_PATH` is a server-side absolute regular file path, or `HOMENAS_MIHOMO_HELPER_SOCKET` can point to the reviewed fixed Unix socket. The browser cannot supply either value.
- Persistent rule apply validates input, stores a backup (`runtime/mihomo-backups/*.bak` for direct mode or `/var/lib/homenas/mihomo-backups/*.bak` for the helper), atomically replaces only the top-level `rules` list, then calls Controller `PUT /configs?force=true`. Reload failure restores the original bytes.
- No live NAS Mihomo service or config was changed by this code change. Enabling the unit variables or installing the root helper requires the separate impact and rollback review required by `AGENTS.md`.
- The NAS currently uses `root:root 600` for `/etc/mihomo/config.yaml`; the reviewed deployment path is `deploy/systemd/homenas-mihomo-helper.py` plus its unit template. The API remains `hongxin` and sends only a validated rules array over the Unix socket.

## Verification

- `npm run typecheck` — passed.
- `npm run build` — passed; regenerated `frontend/static/main.js`.
- `python -m compileall -q backend/homenas backend/tests` — passed.
- `python scripts/smoke_test.py` — passed.
- Temporary-file write/backup/rollback check — passed.
- Chrome headless shell snapshot at 1440×900, 390×844 and 360×800 — no document horizontal overflow observed; authenticated NAS/Mihomo fixture not available locally.
- `pytest` — unavailable on this Windows environment (`pytest` module not installed).
