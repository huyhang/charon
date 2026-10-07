# Charon

A small, API-first service for a Synology NAS. Send it a magnet link and it downloads the
torrent through Download Station, tracks progress, then renames and moves the result
according to your post-download rules. Subscribe it to RSS feeds of magnet links to see
what's new at a glance, and which of it your rules would file.

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
| `POST /downloads` `{magnet, rule_id?}` | Submit a magnet; `rule_id` forces a rule. `202` + new job, or `200` + the existing job if the torrent is already in Charon (`409 torrent_exists` if that job has another rule) |
| `GET /downloads?status=&limit=&cursor=` | List jobs, newest first, cursor-paginated |
| `GET /downloads/summary` | Jobs per status across all jobs, and the combined download speed |
| `GET /downloads/{id}` | Job status and progress |
| `DELETE /downloads/{id}` | Cancel a queued, downloading or completed job |
| `POST /downloads/{id}/retry` | Retry a failed job (a failed download gets a fresh task) |
| `GET/POST /rules`, `GET/PUT/DELETE /rules/{id}` | Manage rules. `PUT` with `version` (or `If-Match`) refuses to overwrite a newer edit |
| `POST /rules/reorder` `{ids}` | Put every rule in a new order at once |
| `POST /rules/preview` `{name, rule_id? \| rule?}` | Dry run: what a name would become, under the saved rules or an unsaved draft `rule` |
| `GET/POST /feeds`, `GET/PUT/DELETE /feeds/{id}` | Manage feed subscriptions (see [Feeds](#feeds)) |
| `POST /feeds/preview` `{url}` | Read a feed without subscribing: title, counts, newest items checked against the rules |
| `POST /feeds/refresh` | Fetch every enabled feed now (paused ones are skipped) |
| `POST /feeds/{id}/refresh` | Fetch one feed now |
| `GET /feeds/{id}/url` | A feed's whole address, passkey included (admin only) |
| `GET /feeds/items?feed_id=&match=&unseen=&q=&limit=&cursor=` | Items from every feed, newest first, each with its matching rule and download |
| `POST /feeds/items/{info_hash}/download` `{rule_id?}` | Download an item (`200` if it's already in Charon) |
| `POST /feeds/items/seen` `{info_hashes}` | Mark exactly these items as seen |
| `POST /feeds/items/seen-all` `{up_to, feed_id?, match?, q?}` | Mark everything in a view as seen, if first seen at or before `up_to` |
| `GET /feeds/summary` | Unseen items, in total and per feed |
| `GET /events?after=&limit=&type=` | What happened since a cursor (see [For scripts and agents](#for-scripts-and-agents)) |
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

Errors always look like
`{"error": {"code": "...", "message": "...", "hint": "...", "retryable": false}}`: a stable
`code`, a `hint` saying what to do about it in plain language (or `null`), and whether
sending the same request again later may work. Validation errors add field-level `details`,
and some others add specifics there too (e.g. which job already has a torrent). Anything
unexpected is a `500` with `internal_error`, in the same shape. A job's `error` has a `hint` too.

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

- A rule may carry a `description` saying why it exists. Every save bumps its `version`,
  also sent as the `ETag`; send the `version` you loaded with `PUT` (or the ETag as
  `If-Match`), and the save fails with `409 rule_changed` instead of overwriting someone else's
  edit. `POST /rules/reorder` re-spaces priorities 10, 20, 30… in one go, and fails with
  `409 rules_changed` if any rule was added, removed or edited meanwhile; `details` lists ids
  that are unknown or missing.
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

### Feeds

Subscribe to RSS feeds whose items link to magnets (in `<link>`, an `<enclosure>`, or the
`<guid>`); items without one are skipped. Subscribing twice to the same address is
`409 feed_exists`. Charon checks each enabled feed every
`refresh_minutes` (5 minutes to a day, default 15), politely: it sends the feed's `ETag` and
`Last-Modified` back, so an unchanged feed isn't downloaded again.

- **One list of items.** `GET /feeds/items` merges every feed, newest `published_at` first.
  An item is a torrent, identified by its info hash, so one listed by two feeds is one item
  with both feeds. Items without a `<pubDate>` are dated when Charon first saw them
  (`published_estimated: true`).
- **Checked against the rules as they are now.** Each item says which rule would file it and
  what it would be called (`match`), or why that rule can't apply to it (`match_error`).
  Editing a rule changes this immediately. Rules see the magnet's name (`dn`), which is what
  Download Station will call the download, or the item's title if there is none.
- **In Charon already?** `job` is the newest download of the same torrent, however it was
  added (from the feed, or by pasting the magnet). Downloading an item that's already in
  Charon returns that job; one whose job was cancelled or failed starts afresh.
- **New and seen.** Items are new until marked seen. The UI marks exactly the new items it
  showed when you switch feed, filter or search, leave the page, or leave the tab, so items a
  filter hid or that you hadn't loaded stay new. **Mark all seen** marks the whole view (its
  feed, filter and search), up to the newest item shown. Seen state is stored in Charon, so
  every device agrees.
- **Auto-download** (per feed, off by default) downloads new items that match a rule: items
  that feed first lists after you turn it on (even if another feed listed them earlier), never
  its backlog. An item dated more than a day before you turned it on is an old release listed
  again, and is left alone. A torrent that is or was in Charon, even cancelled or failed, is
  never taken again. Paused feeds never auto-download. If Download Station can't take an item,
  `auto_error` says why and it's tried again on the next refresh, without holding up the rest.
  These downloads are credited to `auto-download`.
- **Addresses are secrets.** Feed URLs often hold a passkey, so responses mask them
  (`https://tracker.example/rss?passkey=••••`), errors and logs name only the host, and only
  admin keys can read the whole address (`GET /feeds/{id}/url`) or change it. Any key can
  subscribe.
- **Health.** A feed that can't be fetched or read keeps its items and reports `last_error`
  with a hint (unreachable, an HTTP error, not RSS, no magnet links, too large, or something
  Charon couldn't make sense of). It's retried on its next check. Addresses with an invalid
  host or port are refused when you subscribe.
- Items stay while a feed lists them, plus 30 days after. A paused or failing feed may still
  list them, so its items are kept as of its last successful read.

### For scripts and agents

Charon is meant to be driven by scripts and, someday, an AI agent as well as by people:

- **Who did what.** Jobs record `created_by`, and rules and feeds record `created_by` and
  `updated_by`: the name and id of the API key that made the change. Issue each script or
  agent its own key and you can tell their changes apart.
- **Safe to retry.** Submitting a torrent that's already in Charon (same info hash, not
  cancelled or failed) returns the existing job with `200`, or `409 torrent_exists` with the
  job's id in `details` if you asked for another rule. `POST /downloads`, `/rules` and `/feeds`
  accept an `Idempotency-Key` header: repeating a request with the same key returns what the
  first one created, with `200`, for a day, even if both arrive at once. Keys belong to the API
  key that sent them, so two clients can't collide. Reusing a key for a different request is
  `409 idempotency_key_reused`.
- **Events.** `GET /events?after=<cursor>` lists what happened since the cursor, oldest first:
  `job.created`, `job.status_changed`, `rule.created` / `updated` / `deleted`,
  `rules.reordered`, `feed.created` / `updated` / `deleted`, `feed.health_changed`,
  `feed_item.added` and `feed_item.downloaded`, each with its actor. `rule.updated` and
  `feed.updated` list the names of the fields that `changed` (never a feed's address itself).
  Pass the returned `cursor` as `after` next time to follow along; filter with `type=`
  (repeatable). Events are kept for 30 days.

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
sign in with an API key. Over HTTPS it also installs as an app (PWA); see
[HTTPS over Tailscale](#https-over-tailscale) and [Installing on iPhone](#installing-on-iphone).

- **Downloads:** paste a magnet link (into the bar or anywhere on the page) and see which
  rule will match and what the file will be called before you submit. Live progress, filters,
  a detail drawer with the job's timeline, and plain-language fixes for every failure.
- **Feeds:** an inbox of every feed's items, grouped by day, newest first, with what's new
  since your last visit. Each item shows the rule that would file it (expand it for the
  rename and folder), or offers to create a rule from it. One-tap download (or pick the rule),
  multi-select, filters (matches a rule / no rule), search, and keyboard shortcuts (`j`/`k`,
  `x`, `d`, `⏎`, `/`). Add a feed by pasting its address anywhere on the page: Charon reads it
  and checks it against your rules before you subscribe. An unread badge sits on the nav.
- **Rules:** drag to reorder priorities, toggle rules on and off, and edit them with a step
  builder, a folder browser limited to `CHARON_RULE_ROOTS`, and a test bench that runs your
  unsaved draft on the server as you type.
- **API keys** (admins): issue a key and see it once, revoke with a confirmation.
- ⌘K / Ctrl+K command palette, light and dark themes, phone layout.

### HTTPS over Tailscale

Tailscale already encrypts traffic between your devices, so plain `http://` is safe on your
tailnet. HTTPS is still worth having for the browser's sake: installing as an app needs it,
and browsers stop marking the page "Not secure". If Tailscale runs on the NAS, it can provide
HTTPS without touching DSM:

1. In the Tailscale admin console, under **DNS**, enable **MagicDNS** and **HTTPS
   Certificates**.
2. Over SSH on the NAS, have Tailscale serve Charon over HTTPS:

   ```bash
   sudo tailscale serve --bg http://127.0.0.1:8080
   ```

   If `tailscale` isn't on your `PATH`, it's `/var/packages/Tailscale/target/bin/tailscale`.
   `--bg` keeps the setting across reboots. Check it with `tailscale serve status`. To stop
   serving Charon, run `sudo tailscale serve --https=443 off`; `tailscale serve reset`
   would also stop every other service the NAS serves.
3. Open `https://<nas-name>.<tailnet>.ts.net`. The first visit can take a few seconds while
   Tailscale gets a certificate. It renews the certificate itself, so you don't need the
   scheduled root scripts some guides suggest (those install the certificate into DSM, which
   Charon doesn't need).

Point `serve` at an address Charon listens on. `127.0.0.1` works when `CHARON_BIND_IP` is
`0.0.0.0` (the default) or `127.0.0.1`. If you bound Charon to the LAN IP, use that instead,
e.g. `http://192.168.1.10:8080`. Binding to `127.0.0.1` makes the Tailscale HTTPS address
the only way in.

**Serving other services too.** The NAS can serve several services this way; each needs its
own HTTPS port or path. Running `serve` again for a port and path already in use replaces
what was there, so give each service its own:

```bash
sudo tailscale serve --bg http://127.0.0.1:8080                        # Charon: https://<nas>.<tailnet>.ts.net/
sudo tailscale serve --bg --https=8443 http://127.0.0.1:9000           # https://<nas>.<tailnet>.ts.net:8443/
sudo tailscale serve --bg --set-path /other http://127.0.0.1:9001      # https://<nas>.<tailnet>.ts.net/other
sudo tailscale serve status                                            # everything being served
```

A separate port works for any service. A path only works for apps that support running
under a sub-path. Charon doesn't, so keep it at `/` (or on its own port) and give paths to
the others. Stop one service at a time with `off` on the same flags, e.g.
`sudo tailscale serve --https=8443 off` or `sudo tailscale serve --set-path /other off`.

Certificates are recorded in public Certificate Transparency logs, so your NAS and tailnet
names become publicly visible. Nothing becomes reachable, but pick names you don't mind
being seen.

### Installing on iPhone

1. Connect the iPhone to your tailnet with the Tailscale app.
2. In Safari, open Charon, ideally at its `https://…ts.net` address (see above).
3. Tap **Share → Add to Home Screen → Add**.
4. Open Charon from the home screen and sign in. Home-screen apps keep their own storage,
   separate from Safari, so you sign in again. A key issued just for the phone
   (**API keys → Issue key**) can later be revoked on its own.

It opens full screen with Charon's icon and the phone layout. Over HTTPS it keeps its
interface cached, so it opens instantly and updates itself in the background. Over plain
HTTP it's a full-screen shortcut that loads everything over the network each time.

iOS doesn't let web apps receive shares or open `magnet:` links, so tapping a magnet won't
open Charon. Long-press it, choose **Copy**, then paste it into Charon's magnet field, which
shows the matching rule before you submit.

### Developing the UI against the fakes

Needs Node 22.22.2+, 24.15+ or 26+ (the Docker build uses Node 24). No NAS or Docker required:

```bash
make ui-install
make ui-dev          # fake Download Station + Charon + UI on http://localhost:5173 (key: dev-key)
make ui-seed         # in another shell: sample rules, downloads in every state, keys, and feeds
```

`make ui-dev` slows fake downloads to 90 s (`FAKE_DS_DURATION_SECONDS`) so progress is
visible, and accepts the same `CHARON_PORT` / `FAKE_DS_PORT` overrides as `make dev` (pass
them to `make ui-seed` too). In dev builds a **Simulator** button steers the fake: finish or
fail a task, expire sessions, reset, and publish to, break or heal its feeds (then Charon
refreshes, so the inbox shows the change at once). It is compiled out of production builds.

`make ui-seed` subscribes Charon to the fake's two feeds (`/feeds/tv.xml`, `/feeds/anime.xml`),
whose items cover every case: each sample rule, no rule, no date, a `.torrent` link that is
skipped, the same torrent in both feeds, one already in Charon and one downloaded. It then
marks everything seen and publishes one new item to each, so the inbox opens with something
new.

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
  paused in background tabs. Each poll re-fetches every loaded page, so the list loads 25 at a
  time and stops at the newest 100 downloads per filter (older ones stay in Charon, and
  `/downloads/<id>` still opens them). The totals above the list come from
  `GET /downloads/summary`, so they count every job, not just the loaded pages.
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
| `POST /_control/reset` | Clear all tasks and sessions, and restore the sample feeds |
| `GET /feeds/{tv,anime}.xml` | Sample RSS feeds of magnet links, dated relative to when the fake started (honours `If-None-Match`) |
| `GET /_control/feeds` | List the fake feeds and their items |
| `POST /_control/feeds/{slug}/publish` `{name?}` | Add an item dated now |
| `POST /_control/feeds/{slug}/break` `{mode}` | Make the feed answer `503` (`http_error`) or HTML (`bad_xml`) |
| `POST /_control/feeds/{slug}/heal` | Serve the feed normally again |

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
  ports/      interfaces: Downloader, FeedFetcher, EventLog, stores, FileOps, Clock
  services/   DownloadService, RuleService, ApiKeyService, DestinationService, PostProcessor,
              Watcher, FeedService, FeedInbox, FeedRefresher, AutoDownloader, EventService,
              IdempotencyService, Housekeeper
  adapters/   download_station/, sqlite/ (with migrations.py), http_feed_fetcher.py, local_fs.py
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
watcher and API calls (e.g. cancel) cannot overwrite each other. A feed poller looks for
feeds due a refresh every `CHARON_FEED_POLL_INTERVAL_SECONDS`, and a housekeeper prunes old
events, idempotency keys and feed items hourly.

The SQLite schema is versioned with `PRAGMA user_version`: `adapters/sqlite/migrations.py`
lists the changes since the first release, and an existing database picks up the ones it is
missing when Charon starts.

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
