# Charon

A small, API-first service for a Synology NAS. Send it a magnet link and it downloads the
torrent through Download Station, tracks progress, then renames and moves the result
according to your post-download rules.

It is meant to be reached only from your LAN or Tailscale.

## Quick start (no NAS, no Docker)

```bash
python3.12 -m venv .venv
make install
make test        # unit tests
make e2e         # end-to-end: starts Charon + a fake Download Station in-process
make dev         # run Charon on :8080 against the fake Download Station on :5000
make smoke       # in another shell: curl walkthrough; fails unless the file is renamed and moved
make dev-e2e     # in another shell: end-to-end suite against `make dev`
make lint        # ruff lint + format check (`make fmt` fixes)
make coverage    # backend and UI tests with coverage; fails below 90% (see Test coverage)
make check       # everything a change must pass: lint, types, formatting, coverage
make ui-dev      # the web UI against the fakes on http://localhost:5173; see Web UI below
```

Ports are configurable: `make dev CHARON_PORT=18080 FAKE_DS_PORT=15000`, and pass the same
values to `make smoke` / `make dev-e2e`. Interactive API docs: `/api/v1/docs`.

## API

Every endpoint lives under `/api/v1`. All except `/health` require an `X-API-Key` header
when `CHARON_ADMIN_API_KEY` is set (see [API keys](#api-keys)). Paths below omit the prefix.

| Method & path | Purpose |
|---|---|
| `POST /downloads` `{magnet, rule_id?}` | Submit a magnet; `rule_id` forces a rule. Returns `202` + job |
| `GET /downloads?status=&limit=&cursor=` | List jobs, newest first, cursor-paginated |
| `GET /downloads/summary` | Jobs per status across all jobs, and the combined download speed |
| `GET /downloads/{id}` | Job status and progress |
| `DELETE /downloads/{id}` | Cancel a queued, downloading or completed job |
| `POST /downloads/{id}/retry` | Retry a failed job (a failed download gets a fresh task) |
| `GET/POST /rules`, `GET/PUT/DELETE /rules/{id}` | Manage rules |
| `POST /rules/preview` `{name, rule_id? \| rule?}` | Dry run: what a name would become, under the saved rules or an unsaved draft `rule` |
| `GET /destinations/roots` | The folders rule destinations must be inside |
| `GET /destinations/folders?path=` | Folder names directly inside `path` (never files), for picking a destination |
| `POST /api-keys` `{name, role?}` | Issue a key (admin only). The secret is returned once |
| `GET /api-keys`, `GET /api-keys/{id}` | List / inspect keys (admin only; secrets never shown) |
| `DELETE /api-keys/{id}` | Revoke a key immediately (admin only) |
| `GET /auth/me` | Who the presented key belongs to (name, role) |
| `GET /health` | Liveness and downloader reachability |

A job moves through `queued → downloading → completed → processing → done`, or ends in
`failed` / `cancelled`:

```json
{
  "id": "4f1c2a9e-...",
  "status": "done",
  "name": "Some.Show.S01E01.XYZ.1080p.mkv",
  "magnet": "magnet:?xt=urn:btih:...",
  "progress": {"percent": 100.0, "size_bytes": 1500000000, "downloaded_bytes": 1500000000,
               "download_speed_bps": null, "eta_seconds": null},
  "processing": {"rule_id": "r-123", "final_path": "/media/tv/Some.Show.S01E01.ABC.1080p.mkv"},
  "error": null,
  "created_at": "...", "updated_at": "...", "completed_at": "..."
}
```

Errors always look like `{"error": {"code": "...", "message": "..."}}`.

### Rules

```json
{
  "name": "tv",
  "priority": 10,
  "match_type": "glob",
  "pattern": "*XYZ*",
  "steps": [{"op": "replace", "find": "XYZ", "replace": "ABC"},
            {"op": "regex_replace", "find": "\\.1080p", "replace": ""}],
  "destination": "/media/tv"
}
```

- Enabled rules are tried in ascending `priority`; the first whose `pattern` (glob or regex)
  matches the download name wins. Equal priorities go to the older rule (`created_at`), and
  editing a rule keeps its place. A submission's `rule_id` overrides matching.
- Steps run in order on the top-level item name (the file, or the torrent's root folder),
  and the whole item is moved into `destination`.
- Regex patterns and `regex_replace` steps use Python regex syntax (through the `regex`
  module, which also accepts extras such as `\p{L}`). A regex pattern matches anywhere in
  the name; a glob must match all of it. Each regex gets one second per name, so a runaway
  pattern such as `(a|aa)+$` fails the job with `rule_timeout` (preview answers `422`)
  instead of hanging Charon.
- If nothing matches, the job finishes as `done` and the item stays in the download folder.
- Destinations must be inside a directory listed in `CHARON_RULE_ROOTS` (set by whoever
  deploys Charon, not through the API). Anything else is rejected with
  `destination_not_allowed`, both when the rule is saved and again, with symlinks
  resolved, when files are moved. Charon's database directory (and `CHARON_UI_DIR`, if set)
  is always off-limits, even under a root like `/`.
- An existing item at the destination is never overwritten: the job fails with
  `destination_exists`. A symlink there counts, even a broken one, so Charon never writes
  through it to wherever it points. Fix it, then `POST /downloads/{id}/retry`.
- If Charon can't read or write a folder involved, the job fails with `filesystem_error` or
  `move_failed` and the OS message. Fix the permissions, then retry. A job never stays stuck
  in `processing`: anything unexpected fails it with `internal_error` (details in the log).
- After a successful move, the task is removed from Download Station (seeding stops).

### API keys

- `CHARON_ADMIN_API_KEY` is the bootstrap admin key. If it is unset, auth is disabled: every
  endpoint is open and `/api-keys` answers `409 auth_disabled`.
- Use the admin key to issue one key per device or script:

  ```bash
  curl -s -H "X-API-Key: $ADMIN" -H 'Content-Type: application/json' \
    http://nas:8080/api/v1/api-keys -d '{"name": "phone", "role": "client"}'
  ```

  The response contains `key` (shown only once) and `prefix` (shown in listings, so you can
  tell keys apart). Only a SHA-256 hash of the key is stored.
- Roles: `client` keys can use downloads and rules; `admin` keys can also manage keys.
- `DELETE /api-keys/{id}` revokes a key. It is rejected from the very next request, with no
  restart. Revoked keys stay listed with `revoked_at` for reference.
- The bootstrap key is not stored in the database and cannot be revoked through the API. To
  rotate it, change `CHARON_ADMIN_API_KEY` and recreate the container. Consider keeping it
  for administration only and giving every client its own issued key.

## Web UI

Charon ships with a web UI in `ui/` (React, TypeScript, Vite, Tailwind, shadcn/ui). The
Docker image builds it and serves it at `/`, so on the NAS just open `http://nas:8080` and
sign in with an API key. It installs as an app (PWA) from the browser menu.

- **Downloads:** paste a magnet link (into the bar or anywhere on the page) and see which
  rule will match and what the file will be called before you submit. Live progress, filters,
  a detail drawer with the job's timeline, and plain-language fixes for every failure.
- **Rules:** drag to reorder priorities, toggle rules on and off, and edit them with a step
  builder, a folder browser limited to `CHARON_RULE_ROOTS`, and a test bench that runs your
  unsaved draft on the server as you type.
- **API keys** (admins): issue a key and see it once, revoke with a confirmation.
- ⌘K / Ctrl+K command palette, light and dark themes, phone layout.

### Developing the UI against the fakes

Needs Node 22.22.2+, 24.15+ or 26+ (the Docker build uses Node 24). No NAS or Docker required:

```bash
make ui-install
make ui-dev          # fake Download Station + Charon + UI on http://localhost:5173 (key: dev-key)
make ui-seed         # in another shell: sample rules, downloads in every state, and keys
```

`make ui-dev` slows fake downloads to 90 s (`FAKE_DS_DURATION_SECONDS`) so progress is
visible, and accepts the same `CHARON_PORT` / `FAKE_DS_PORT` overrides as `make dev` (pass
them to `make ui-seed` too). In dev builds a **Simulator** button steers the fake: finish or
fail a task, expire sessions, reset. It is compiled out of production builds.

| Command | Purpose |
|---|---|
| `make ui-test` | Unit and component tests (Vitest, Testing Library) |
| `make ui-coverage` | The same with coverage; fails below 90% (HTML report in `ui/coverage/`) |
| `make ui-lint` / `make ui-fmt` | Type check and Prettier check / format |
| `make ui-e2e` | Browser tests against a running `make ui-dev` (first: `cd ui && npx playwright install chromium`) |
| `make ui-build` | Production build into `ui/dist` |
| `make ui-serve` | Build, then let Charon serve it on `:8080` against the fake, as on the NAS |
| `make ui-api` | Regenerate `ui/src/api/schema.d.ts` from `docs/openapi.json` (`make openapi` does this too) |

How it fits together:

- **Typed client.** `ui/src/api/schema.d.ts` is generated from the committed OpenAPI spec, so
  an API change that breaks the UI fails its type check.
- **Inversion of control.** Components never call `fetch`: they get a `CharonClient`
  interface from React context. The app injects the HTTP implementation; tests inject a fake
  (`ui/src/test/fakeClient.ts`). Formatting, matching, diffing and error hints are pure
  functions in `ui/src/lib`.
- **Live data** is polled: every 1.5 s while anything is in flight, every 15 s otherwise,
  paused in background tabs. The totals above the list come from `GET /downloads/summary`,
  so they count every job, not just the loaded page.
- **Sessions.** The key is re-checked every 30 s and when the tab regains focus, so a revoked
  key signs the browser out on any page. If Charon can't be reached when the UI opens, it
  says so and retries every few seconds instead of asking for a key.
- **Copying** a key or hash works over plain HTTP too: browsers only offer the Clipboard API
  on secure pages, so the UI falls back to copying a selection.
- **Serving.** `CHARON_UI_DIR` points Charon at a built UI (the image sets it). Unknown
  non-API paths fall back to `index.html`, so client-side routes survive a reload. To run the
  dev server against another Charon, use `CHARON_URL=http://nas:8080 npm run dev` in `ui/`,
  or allow its origin with `CHARON_CORS_ORIGINS`.

## Deploying on Synology

See **[docs/synology-deployment.md](docs/synology-deployment.md)** for a step-by-step guide:
packages, a dedicated DSM user, folders and permissions, configuration, Container Manager,
verification with a real download, access restrictions, updates, backups and
troubleshooting.

In short: create a DSM user with Download Station access, copy the repo to the NAS,
`cp docker/.env.example docker/.env` and fill it in, then create a Container Manager project
from the `docker/` folder (or run `sudo docker compose up -d --build` inside it).

## Testing against a fake Download Station

`fake_ds/` is a standalone FastAPI app implementing the Synology Web API calls Charon uses
(API discovery, login, create/getinfo/list/delete task, info). Like a DSM 7 NAS, it serves
each API only at the path `SYNO.API.Info` reports, rejects unsupported versions, and uses the
response types from Synology's API guide (string sizes, `"status_extra": null`, error `404`
for unknown task ids), so a client that guesses paths or shapes fails here too. Tasks progress over
`FAKE_DS_DURATION_SECONDS`, then a placeholder file named after the magnet's `dn` is written
into `FAKE_DS_DOWNLOAD_DIR`, so rename/move really happens.

Test-only control endpoints:

| Endpoint | Effect |
|---|---|
| `GET /_control/tasks` | List tasks |
| `POST /_control/tasks/{id}/complete` | Finish a task now |
| `POST /_control/tasks/{id}/fail` `{detail}` | Fail a task |
| `POST /_control/sessions/expire` | Invalidate sessions (tests re-login) |
| `POST /_control/reset` | Clear all tasks and sessions |

Three ways to stand it up:

- `make e2e`: everything in-process, temporary folders. Best for CI.
- `make dev` + `make dev-e2e` / `make smoke`: two local processes, files under `./var`.
- `make docker-dev` + `make docker-e2e`: both containers via `docker/docker-compose.dev.yml`.

## Test coverage

Both halves must keep at least 90% coverage; `make coverage` (and `make check`) fail below it.

| Command | Measures | Threshold configured in |
|---|---|---|
| `make py-coverage` | `charon/` and `fake_ds/`, line and branch, over the unit and in-process e2e suites. HTML report in `htmlcov/` | `[tool.coverage.*]` in `pyproject.toml` |
| `make ui-coverage` | `ui/src`, statements, branches, functions and lines each. HTML report in `ui/coverage/` | `test.coverage.thresholds` in `ui/vite.config.ts` |

Generated and test-only code is left out: the OpenAPI types (`schema.d.ts`), test helpers, and
`ui/src/main.tsx`, which only wires real implementations together and is exercised by
`make ui-e2e`.

## Architecture

```
charon/
  domain/     models and pure rename/match logic
  ports/      interfaces: Downloader, JobStore, RuleStore, ApiKeyStore, FileOps, Clock
  services/   DownloadService, RuleService, ApiKeyService, DestinationService, PostProcessor, Watcher
  adapters/   download_station/, sqlite/, local_fs.py
  api/        FastAPI routers, schemas, auth, error mapping
  bootstrap.py  composition root: the only module that knows concrete adapters
fake_ds/      fake Download Station, plus `python -m fake_ds.seed` for sample data
docker/       Dockerfiles, compose files (NAS and local fake stack), .env.example
ui/           web UI (React + Vite); built into the Docker image
tests/unit    fast, isolated tests using in-memory fakes (tests/unit/fakes.py)
tests/e2e     scripted API flows against Charon + fake Download Station
```

Services depend only on ports; `bootstrap.py` wires the adapters in. A background watcher
polls the downloader every `CHARON_POLL_INTERVAL_SECONDS`, updates jobs, and runs
post-processing for completed ones. Job updates are compare-and-set on status, so the
watcher and API calls (e.g. cancel) cannot overwrite each other.

### Adding another downloader (e.g. Transmission)

1. Implement `charon.ports.downloader.Downloader` (`add`, `get`, `remove`, `is_available`)
   in `charon/adapters/transmission/`, mapping its states onto `BackendStatus`.
2. Register a factory in `DOWNLOADERS` in `charon/bootstrap.py` and extend the `downloader`
   literal and settings in `charon/config.py`.
3. Set `CHARON_DOWNLOADER=transmission`. Nothing else changes.

## Configuration

All settings are `CHARON_*` environment variables (see `charon/config.py` and `docker/.env.example`).

## Known limitations

- The Download Station adapter targets DSM 7. As Synology's Download Station Web API guide
  prescribes, it asks `SYNO.API.Info` (`/webapi/query.cgi`) where each API lives and which
  versions it supports, and reports `downloader_unsupported` if something is missing. It
  creates tasks with `SYNO.DownloadStation2.Task`, which returns the task id but is not in
  that guide, and uses the documented `SYNO.DownloadStation.Task` v1 for status and deletion.
  Status parsing is tested against the guide's own example responses; task creation can only
  be confirmed on a real NAS, so verify it there before relying on it.
- Download Station must not be configured to move completed files elsewhere, or Charon
  will not find them in the download folder.
