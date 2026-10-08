# Deploying Charon on a Synology NAS

This guide takes you from a fresh NAS to a working Charon instance that downloads through
Download Station and files the results into your library. It takes about 30 minutes.

Throughout, replace these example values with your own:

| Example | Meaning |
|---|---|
| `192.168.1.10` | Your NAS's LAN IP |
| `/volume1` | The volume your shared folders live on |
| `downloads` | The shared folder Download Station saves into |
| `media` | The shared folder holding your library |

## Before you start

- **DSM 7.2 or later**, on a model that supports **Container Manager**. Check the package
  list for your model in Package Center.
- An **administrator** DSM account, used for setup only.
- About 300 MB of free space for the Charon image.

## 1. Install the packages

In **Package Center**, install:

- **Download Station**
- **Container Manager**. This also creates a `docker` shared folder.

## 2. Prepare the shared folders

In **Control Panel → Shared Folder**, make sure these exist (create any that are missing):

| Shared folder | Purpose |
|---|---|
| `downloads` | Where Download Station writes in-progress and finished downloads |
| `media` | Your library: where rules move finished downloads |
| `docker` | Created by Container Manager; Charon's code and database go here |

Then in **File Station**, create these folders inside `docker`:

```
docker/
  charon/
    app/     <- Charon's source code and configuration
    data/    <- Charon's database
```

> **Faster moves:** on Btrfs volumes, every shared folder is a separate subvolume, so
> moving a file from `downloads` to `media` is a full copy followed by a delete. For large
> files that is slow and briefly needs twice the space. If that matters to you, see
> [Making moves instant](#making-moves-instant) before continuing.

## 3. Create a dedicated user for Charon

Charon logs in to Download Station with its own account, and the container runs as this
user so that files it creates belong to it.

1. Go to **Control Panel → User & Group → Create**.
2. Name it `charon` and give it a strong password. Store it in a password manager; you'll
   need it in step 6.
3. **Groups:** leave it in `users` only. Don't add it to `administrators`.
4. **Shared folder permissions:** *Read/Write* on `downloads`, `media` and `docker`. *No
   access* on everything else.
5. **Application permissions:** allow **Download Station**. Deny everything else.
6. Finish the wizard.

Two account settings will break Charon if you leave them on:

- **2-factor authentication must be off for this account.** Charon can't enter a one-time
  code, so the login fails with Synology error `403`.
- **Auto Block:** if Charon ever logs in with a wrong password repeatedly, DSM may block the
  container's IP (Synology error `407`). See [Troubleshooting](#troubleshooting) for how to
  allow it.

### Find the user's UID and GID

You need these numbers so the container writes files as `charon`. This needs SSH, once:

1. Go to **Control Panel → Terminal & SNMP → Enable SSH service → Apply**.
2. From your computer, run `ssh <your-admin-user>@192.168.1.10`, then:

   ```bash
   id charon
   # uid=1030(charon) gid=100(users) groups=100(users)
   ```

3. Note the `uid` (here `1030`) and `gid` (here `100`).

Keep the SSH session open; later steps use it. You can disable SSH again at the end.

## 4. Configure Download Station

Download Station keeps the default download folder per DSM user, and Charon adds its tasks
as `charon`, so set it for that account:

1. Sign in to DSM as `charon`. A private browser window keeps you signed in as yourself
   elsewhere.
2. Open **Download Station → Settings → Location** and set the default destination to
   `downloads`, the same folder as `CHARON_DS_DESTINATION` (step 6).
3. Sign out.

Charon names the folder for every task, but that isn't enough: until `charon` has a default
destination of its own, Download Station leaves its tasks at **Waiting** and they never
start. Your own account's **Location** is separate and only affects downloads you add by
hand.

Leave the BitTorrent settings as you like. Charon removes each task after moving its files,
so seeding limits only matter while a download is still in Download Station.

Don't set up anything in Download Station that moves completed files out of `downloads`,
or Charon won't find them.

## 5. Copy Charon to the NAS

Put the repository's contents into `docker/charon/app`, so that the repository's own
`docker/` folder (Dockerfiles, `docker-compose.yml`, `.env.example`) ends up at
`docker/charon/app/docker`. The first `docker` is the shared folder Container Manager created;
the last is the repository's. Choose either option.

**Option A: File Station (no tools needed)**

1. On GitHub, use **Code → Download ZIP**.
2. In File Station, upload the ZIP to `docker/charon/app` and choose **Extract** in the
   right-click menu.
3. If extraction created a subfolder (e.g. `charon-main/`), move its contents up into
   `app/`.

**Option B: git over SSH** (needs the **Git Server** package, which provides `git`)

```bash
cd /volume1/docker/charon
git clone <your-repo-url> app
```

## 6. Configure Charon

In your SSH session:

```bash
cd /volume1/docker/charon/app/docker
cp .env.example .env
openssl rand -base64 32          # copy the output; it becomes your admin API key
vi .env                          # or edit .env with File Station's Text Editor
```

Set these values in `.env`:

| Setting | Value |
|---|---|
| `PUID` / `PGID` | The `uid` / `gid` from step 3, e.g. `1030` / `100` |
| `CHARON_DATA_DIR` | `/volume1/docker/charon/data` |
| `CHARON_DOWNLOADS_DIR` | `/volume1/downloads`. It must be the same folder as `CHARON_DS_DESTINATION`. |
| `CHARON_MEDIA_DIR` | `/volume1/media` |
| `CHARON_RULE_ROOTS` | `/media`: the container folders rules may move files into (see below) |
| `CHARON_ADMIN_API_KEY` | The `openssl` output |
| `CHARON_DS_URL` | `http://192.168.1.10:5000`. Use the LAN IP: `localhost` points at the container itself. |
| `CHARON_DS_USERNAME` / `CHARON_DS_PASSWORD` | `charon` and its password |
| `CHARON_DS_DESTINATION` | `downloads`: the shared folder name as DSM shows it, without `/volume1` |
| `CHARON_BIND_IP` | See [Restricting access](#restricting-access); `0.0.0.0` is fine to start |

If DSM only accepts HTTPS, use `https://192.168.1.10:5001`. If it has a self-signed
certificate, also set `CHARON_DS_VERIFY_TLS=false`.

### Choose where rules may move files

Rules move files to paths **inside the container**. The default setup mounts
`/volume1/media` at `/media`, so a rule destination of `/media/tv` lands in
`/volume1/media/tv` on the NAS.

`CHARON_RULE_ROOTS` lists the container folders rules are allowed to use. Charon rejects
any other destination (`destination_not_allowed`) when a rule is saved, and checks again,
with symlinks resolved, before every move. Only you control this list, through `.env`; API
keys can't change it. Charon's database directory (`/data`) is always off-limits.

To let rules use another shared folder:

1. Mount it under `volumes:` in `docker/docker-compose.yml`, e.g. `- /volume1/video:/video`.
2. Add it to the roots in `.env`, e.g. `CHARON_RULE_ROOTS=/media,/video`.
3. Recreate the container.

Only list folders that are mounted. A root that isn't a mount would let files land in the
container's own filesystem, where they disappear when the container is recreated.

### Optional: look up official titles on TMDB

The rule editor can look up a show's or movie's official title on
[The Movie Database (TMDB)](https://www.themoviedb.org) and add a step that renames the
release to it, e.g. *Kusuriya no Hitorigoto* to *The Apothecary Diaries*. TMDB's API is free
for non-commercial use, with your own key:

1. Create a free account at themoviedb.org, then open **Settings → API** and request an API
   key for personal use.
2. Copy the **API Read Access Token** (the long one, not the short "API Key").
3. After Charon is running (step 7), open its UI as an admin, go to **Settings → Title
   lookup** and paste the token. Nothing needs restarting. (You can instead set
   `CHARON_TMDB_TOKEN` in `.env`; a token saved in Settings takes its place.)

`CHARON_TMDB_LANGUAGE` in `.env` picks the language titles come back in (a code such as
`en-US`, `fr-FR` or `ja`; default `en-US`). Charon never sends TMDB more than 40 requests in
any 10 seconds. Remove the token in Settings (and leave `CHARON_TMDB_TOKEN` empty) to turn
lookups off.

## 7. Build and start the container

Choose either option.

**Option A: Container Manager**

1. Open **Container Manager → Project → Create**.
2. **Project name:** `charon`.
3. **Path:** select `docker/charon/app/docker`.
4. **Source:** *Use existing docker-compose.yml*.
5. Click **Next**, skip **Web portal settings**, then **Next → Done**. Leave *Start the
   project once it is created* ticked.

The first build downloads the Python base image and takes a few minutes. When the project
shows **Running**, continue.

**Option B: SSH**

```bash
cd /volume1/docker/charon/app/docker
sudo docker compose up -d --build     # on older DSM: sudo docker-compose up -d --build
```

If a setting from `.env` doesn't seem to take effect with Option A, use Option B; it always
reads `.env` from the project folder.

## 8. Check that it works

From any computer on your LAN:

```bash
NAS=http://192.168.1.10:8080/api/v1
ADMIN='X-API-Key: <your admin key>'

curl -s $NAS/health
# {"status":"ok","downloader":"reachable"}

curl -s -H "$ADMIN" $NAS/auth/me
# {"name":"bootstrap-admin","role":"admin","key_id":null,"auth_enabled":true}
```

If `downloader` is `unreachable`, see [Troubleshooting](#troubleshooting).

Then open `http://192.168.1.10:8080` in a browser and sign in with your admin key: the web
UI covers everything below (keys, rules with a live test bench, downloads). On a phone, use
**Add to Home Screen** to install it as an app. The curl commands stay useful for scripts.

The interactive API docs are at `http://192.168.1.10:8080/api/v1/docs`. Click
**Authorize**, paste your admin key, and you can try every endpoint from the browser.

## 9. Issue keys for your devices

Keep the admin key for administration, and give each device or script its own key, so you
can revoke one without affecting the others:

```bash
curl -s -H "$ADMIN" -H 'Content-Type: application/json' $NAS/api-keys \
  -d '{"name": "phone", "role": "client"}'
```

Copy the `key` from the response; it is shown only once. To revoke it later:

```bash
curl -s -H "$ADMIN" $NAS/api-keys                       # find its id
curl -s -X DELETE -H "$ADMIN" $NAS/api-keys/<id>
```

## 10. Create a rule and run a real download

This step also confirms Charon works with *your* Download Station. Charon's Download Station
support was built from Synology's API documentation and tested against a fake, so do this
once before relying on it.

1. Create a rule:

   ```bash
   curl -s -H "$ADMIN" -H 'Content-Type: application/json' $NAS/rules -d '{
     "name": "linux isos",
     "pattern": "*.iso",
     "destination": "/media/isos"
   }'
   ```

2. Preview where a file would go, with nothing touched:

   ```bash
   curl -s -H "$ADMIN" -H 'Content-Type: application/json' $NAS/rules/preview \
     -d '{"name": "debian-12.iso"}'
   ```

3. Submit a magnet for a small, legal torrent, such as a Linux distribution ISO from its
   official site:

   ```bash
   curl -s -H "$ADMIN" -H 'Content-Type: application/json' $NAS/downloads \
     -d '{"magnet": "magnet:?xt=urn:btih:..."}'
   ```

4. Check that:
   - the task appears in the **Download Station** UI;
   - `GET $NAS/downloads/<id>` shows the status moving through `downloading` to `done`;
   - the file is in `/volume1/media/isos` in File Station, owned by `charon`;
   - the task is gone from Download Station.

If any of these fail, the job's `error` field and the container log (step 11) say why.

## 11. Logs, updates and backups

**Logs:** **Container Manager → Container → charon → Log**, or run
`sudo docker logs charon` over SSH.

**Updating Charon:**

1. Replace the contents of `docker/charon/app` with the new version (Option A or B from
   step 5). Keep your `docker/.env`, and any `volumes:` lines you added to
   `docker/docker-compose.yml`.
2. Rebuild: **Container Manager → Project → charon → Action → Build**, or over SSH run
   `sudo docker compose up -d --build` in `/volume1/docker/charon/app/docker`.

Jobs, rules and API keys live in `docker/charon/data`, so they survive updates.

**Backups:** include `docker/charon/data` in your **Hyper Backup** task. It holds a single
small SQLite file. For a fully consistent copy, stop the project first, or schedule the
backup when nothing is downloading.

## Restricting access

Charon should only be reachable from your LAN and Tailscale. In order of preference:

1. **Don't forward the port.** Make sure your router has no port forward for `8080`.
2. **Bind to one interface.** Set `CHARON_BIND_IP` to the NAS's LAN IP (e.g.
   `192.168.1.10`) and recreate the container. Tailscale devices can then reach Charon if
   the NAS (or another device) advertises your LAN as a Tailscale subnet route.
3. **Firewall rules.** If you need `0.0.0.0` (e.g. Tailscale runs directly on the NAS and
   you want both addresses), add rules under **Control Panel → Security → Firewall** that
   allow port `8080` from `192.168.1.0/24` and `100.64.0.0/10` (Tailscale) and deny it
   otherwise. Docker's port publishing can bypass host firewall rules on some systems, so
   test from a device outside those ranges and confirm the connection is refused.

With `CHARON_ADMIN_API_KEY` set, every request also needs a valid key.

## Making moves instant

A move between two mounts is a copy plus delete. It's an instant rename only when the
source and destination are on the same filesystem **and** the same container mount. To get
that:

1. Keep downloads and library inside **one** shared folder, e.g. `/volume1/data/downloads`
   and `/volume1/data/media`. Separate shared folders are separate Btrfs subvolumes, so
   moves between them are always copies.
2. Mount that shared folder once, at the same path inside the container. In
   `docker/docker-compose.yml`, replace the `/downloads` and `/media` volume lines with:

   ```yaml
         - /volume1/data:/volume1/data
   ```

3. In `.env`, set `CHARON_DS_DESTINATION=data/downloads`. Then add this under
   `environment:` in `docker/docker-compose.yml`:

   ```yaml
         CHARON_DOWNLOAD_DIR: /volume1/data/downloads
   ```

4. In `.env`, set `CHARON_RULE_ROOTS=/volume1/data/media`, and use real NAS paths in
   rules, e.g. `"destination": "/volume1/data/media/tv"`.
5. Recreate the container.

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| `/health` says `downloader: unreachable` | `CHARON_DS_URL` is wrong or uses `localhost`. From the NAS run `curl 'http://192.168.1.10:5000/webapi/query.cgi?api=SYNO.API.Info&version=1&method=query&query=SYNO.DownloadStation.Task'`; it should answer with `DownloadStation/task.cgi`. Also check Download Station is running. |
| Submitting returns `502` with `downloader_unsupported` | The NAS doesn't offer an API (or version) Charon needs, and the message names it. Install or update Download Station; Charon needs DSM 7 for `SYNO.DownloadStation2.Task`. |
| Submitting returns `502` with `Synology error 400` | Wrong `CHARON_DS_USERNAME` or `CHARON_DS_PASSWORD`. |
| `Synology error 401` / `402` | The `charon` account is disabled, or lacks the Download Station application permission (step 3). |
| `Synology error 403` | 2-factor authentication is on for `charon`. Turn it off for this account. |
| `Synology error 407` | DSM Auto Block blocked the container's IP after failed logins. In **Control Panel → Security → Protection**, remove it from the block list and add the Docker subnet (usually `172.16.0.0/12`) to the allow list. |
| A download stays **Queued** in Charon (**Waiting** in Download Station), but the same magnet starts at once when you add it by hand | The `charon` account has no default destination in Download Station. Set one while signed in as `charon` (step 4). If the waiting task still doesn't start, cancel the job and submit the magnet again. |
| Job fails with `source_missing` | Charon can't see what Download Station wrote: `CHARON_DOWNLOADS_DIR` and `CHARON_DS_DESTINATION` point at different folders. |
| Job fails with `move_failed` or `filesystem_error` (permission denied) | `PUID`/`PGID` don't match `charon`, or `charon` lacks Read/Write on the destination's shared folder or can't open a folder on the way to it. Fix it, then `POST /api/v1/downloads/<id>/retry`. |
| Job fails with `rule_timeout` | A rule's regex took over a second on the download's name, usually because of a nested repeat like `(a+)+`. Simplify it, check it with `POST /api/v1/rules/preview`, then retry the job. |
| Job fails with `internal_error` | Something unexpected went wrong. The container log (step 11) has the details. Retry once the cause is fixed. |
| Job fails with `destination_exists` | A file with the new name is already there. Charon never overwrites. Remove or rename it, then `POST /api/v1/downloads/<id>/retry`. |
| Creating a rule fails with `destination_not_allowed` | The destination is outside `CHARON_RULE_ROOTS`. Add its folder (mounted first) to the roots, or pick a destination inside one. See [Choose where rules may move files](#choose-where-rules-may-move-files). |
| A job fails with `task_missing` | Download Station no longer had the task for 3 checks in a row, and its download wasn't complete in the download folder. Retry: Charon files the download if it has arrived in full, and downloads it again if not. If it keeps happening, check whether something clears tasks in Download Station (its own settings, DS Get, a browser extension, another download manager), and that Download Station's destination is the folder mounted as `CHARON_DOWNLOAD_DIR`. |
| A job fails with `destination_not_allowed` | The rule predates a change to `CHARON_RULE_ROOTS`, or its folder is a symlink pointing outside the roots. Update the rule, then retry the job. |
| A moved file vanished after an update | A folder listed in `CHARON_RULE_ROOTS` isn't mounted. See [Choose where rules may move files](#choose-where-rules-may-move-files). |
| Title lookup asks for a TMDB token | None is set yet. An admin can paste one right there or in **Settings → Title lookup** (see [Optional: look up official titles on TMDB](#optional-look-up-official-titles-on-tmdb)). |
| Saving the token says `metadata_key_wrong_kind` | That's the short API Key. Copy the **API Read Access Token** (the long one) instead. |
| Title lookup says `metadata_auth_failed` | TMDB didn't accept the token. Check it in **Settings → Title lookup**: it must be the **API Read Access Token**, not the short API key. |
| Title lookup says `metadata_unavailable` | Charon couldn't reach `api.themoviedb.org`. From the NAS run `curl -sI https://api.themoviedb.org`. |
| `401` on every request | Missing or wrong `X-API-Key`, or the key was revoked. `GET /api/v1/auth/me` tells you which key the server sees. |
| Project won't start | A required setting is missing from `.env`. `docker compose` names it, e.g. `set CHARON_DS_URL`. |
| Container keeps restarting | Check the log (step 11) for the error. |

When you're done, you can turn SSH off again in **Control Panel → Terminal & SNMP**.
