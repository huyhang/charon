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
| `GET /downloads/{id}` | Job status and progress |
| `DELETE /downloads/{id}` | Cancel a queued, downloading or completed job |
| `POST /downloads/{id}/retry` | Retry a failed job (a failed download gets a fresh task) |
| `GET/POST /rules`, `GET/PUT/DELETE /rules/{id}` | Manage rules |
| `POST /rules/preview` `{name, rule_id?}` | Dry run: what a name would become |
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

## Building a UI

The API is designed so a browser UI can be added without changing it:

- **Typed client.** The OpenAPI spec is committed at `docs/openapi.json` with camelCase
  operation ids (`submitDownload`, `listDownloads`, ...) and documented error responses.
  Generate a TypeScript client from it, e.g. `npx openapi-typescript docs/openapi.json -o
  src/api.ts`. A unit test fails if the API changes without `make openapi` being re-run,
  so contract changes always show up in review. The live spec is at
  `/api/v1/openapi.json`.
- **Login.** Store a key in the browser and call `GET /api/v1/auth/me` to validate it; use
  the returned `role` to show or hide key management.
- **Errors.** Every failure, including unknown routes, is
  `{"error": {"code", "message", "details?"}}`; `details` carries field-level validation
  problems for forms.
- **Serving.** Set `CHARON_UI_DIR` to a built single-page app (with `index.html`) and Charon
  serves it at `/` from the same container: same origin, no CORS. Unknown non-API paths fall
  back to `index.html`, so client-side routes survive a reload.
- **Developing.** Run the UI dev server separately and allow it with
  `CHARON_CORS_ORIGINS=http://localhost:5173` (comma-separated for several).

## Deploying on Synology

See **[docs/synology-deployment.md](docs/synology-deployment.md)** for a step-by-step guide:
packages, a dedicated DSM user, folders and permissions, configuration, Container Manager,
verification with a real download, access restrictions, updates, backups and
troubleshooting.

In short: create a DSM user with Download Station access, copy the repo to the NAS,
`cp .env.example .env` and fill it in, then create a Container Manager project from
`docker-compose.yml` (or run `sudo docker compose up -d --build`).

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
- `make docker-dev` + `make docker-e2e`: both containers via `docker-compose.dev.yml`.

## Architecture

```
charon/
  domain/     models and pure rename/match logic
  ports/      interfaces: Downloader, JobStore, RuleStore, ApiKeyStore, FileOps, Clock
  services/   DownloadService, RuleService, ApiKeyService, PostProcessor, Watcher
  adapters/   download_station/, sqlite/, local_fs.py
  api/        FastAPI routers, schemas, auth, error mapping
  bootstrap.py  composition root: the only module that knows concrete adapters
fake_ds/      fake Download Station
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

All settings are `CHARON_*` environment variables (see `charon/config.py` and `.env.example`).

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
