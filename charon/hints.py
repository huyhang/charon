"""What a person (or an agent) can do about each error code, in plain language.

Kept on the server so every client gets the same advice, not just the web UI.
"""

HINTS: dict[str, str] = {
    # Job failures.
    "destination_exists": (
        "Something with the same name is already at the destination. Move or rename it, then retry."
    ),
    "destination_not_allowed": (
        "The rule's destination is outside the folders Charon may write to. "
        "Edit the rule, then retry."
    ),
    "filesystem_error": (
        "Charon couldn't read or write a folder. Check the folder permissions, then retry."
    ),
    "move_failed": "The file couldn't be moved. Check permissions and free space, then retry.",
    "rule_timeout": "A rule's regex took too long on this name. Simplify the pattern, then retry.",
    "unsafe_name": (
        "A rule renamed this to an unsafe name (e.g. with a slash). "
        "Fix the rule's steps, then retry."
    ),
    "rule_not_found": (
        "The rule was deleted. Reload the rules, or retry the download to match the current ones."
    ),
    "task_missing": "The task disappeared from Download Station. Retry to start a fresh download.",
    "backend_error": (
        "Download Station reported a problem. Check the link is still valid, then retry."
    ),
    "source_missing": (
        "The finished download isn't in the download folder. "
        "Check Download Station's destination matches CHARON_DOWNLOAD_DIR."
    ),
    "invalid_name": "Download Station reported a name Charon can't use as a file name.",
    "internal_error": (
        "Something unexpected went wrong. Charon's log has the details; retrying may help."
    ),
    # Download Station.
    "downloader_error": (
        "Download Station didn't answer as expected. Check it is running, then try again."
    ),
    "downloader_unreachable": (
        "Charon can't reach Download Station. Check the NAS is up and CHARON_DS_URL is right."
    ),
    "downloader_unsupported": "Install or update Download Station on the NAS.",
    "synology_error": "Download Station refused the request. Its log on the NAS may say why.",
    # Requests.
    "invalid_request": "Fix the fields listed in details and send the request again.",
    "invalid_magnet": "Send a magnet link starting with magnet:?",
    "unknown_rule": "Pick a rule that exists; list them with GET /rules.",
    "rule_changed": "Load the rule again to get its latest version, reapply your change, and save.",
    "rules_changed": (
        "Load the rules again, then reorder the current list. details lists any ids that are "
        "unknown or missing."
    ),
    "duplicate_rule_ids": "List each rule exactly once.",
    "invalid_if_match": 'Send the ETag from GET /rules/{id} as If-Match, e.g. "3".',
    "job_changed": "The job changed at the same moment. Load it again and retry.",
    "job_not_found": "Check the job id; list jobs with GET /downloads.",
    "job_not_cancellable": "Only queued, downloading or completed jobs can be cancelled.",
    "job_not_retryable": "Only failed jobs can be retried.",
    "torrent_exists": (
        "The torrent is already in Charon (see details.job_id). Cancel that job first to "
        "download it with another rule."
    ),
    "invalid_cursor": "Pass back the cursor from the previous page unchanged, or start over.",
    "invalid_path": "Send an absolute folder path inside one of the destination roots.",
    "folder_not_found": "Pick a folder that exists; browse from GET /destinations/roots.",
    "api_key_not_found": "Check the key id; list keys with GET /api-keys.",
    "idempotency_key_reused": "Use a new Idempotency-Key for each different request.",
    "unauthorized": "Sign in with a valid API key.",
    "forbidden": "Ask an admin, or use an admin key.",
    "auth_disabled": "Set CHARON_ADMIN_API_KEY to turn on API keys.",
    # Feeds.
    "feed_not_found": "The feed was removed, or the id is wrong. List feeds with GET /feeds.",
    "feed_item_not_found": (
        "The item is no longer in any feed. List current items with GET /feeds/items."
    ),
    "feed_exists": "You're already subscribed to this feed; edit that one instead.",
    "feed_invalid_url": "Use a full http:// or https:// address with a valid host and port.",
    "feed_unreadable": (
        "Charon couldn't make sense of the feed. Its log has the details; Charon tries again "
        "on the next refresh."
    ),
    "feed_unreachable": (
        "Charon couldn't connect to the feed's server. Check the address, and that the NAS "
        "can reach it; Charon tries again on the next refresh."
    ),
    "feed_http_error": (
        "The feed's server refused or failed the request. If the address holds a passkey, "
        "check it is still valid."
    ),
    "feed_too_large": "The feed is too big to read. Ask the site for a smaller feed.",
    "feed_not_rss": "This address doesn't serve an RSS feed. Check you copied the RSS link.",
    "feed_no_magnets": (
        "The feed has items, but none link to a magnet. Look for the site's magnet RSS option."
    ),
    # Title lookup.
    "invalid_query": "Search for a title of at least 2 characters.",
    "metadata_provider_not_found": "List the providers Charon knows with GET /metadata/providers.",
    "metadata_not_configured": (
        "Title lookup needs a TMDB token. An admin can add one in Settings, "
        "or set CHARON_TMDB_TOKEN."
    ),
    "invalid_metadata_key": "Paste the whole key the provider gave you, with nothing around it.",
    "metadata_key_wrong_kind": (
        "On themoviedb.org (Settings → API), copy the API Read Access Token: the long one, "
        "not the short API Key."
    ),
    "metadata_rate_limited": (
        "Charon is holding back to stay within TMDB's request limit. "
        "Wait a little (see Retry-After), then search again."
    ),
    "metadata_unavailable": (
        "Charon couldn't get an answer from TMDB. Check the NAS can reach it, then try again."
    ),
    "metadata_auth_failed": (
        "TMDB didn't accept Charon's token. An admin can check it in Settings: it must be the "
        "API Read Access Token, not the short API Key."
    ),
    "metadata_error": "TMDB answered in a way Charon didn't expect. Try again in a moment.",
}

# Sending the same request again later may work without changing anything.
RETRYABLE = frozenset(
    {
        "downloader_unreachable",
        "downloader_error",
        "synology_error",
        "job_changed",
        "internal_error",
        "feed_unreachable",
        "feed_http_error",
        "feed_unreadable",
        "metadata_rate_limited",
        "metadata_unavailable",
        "metadata_error",
    }
)


def hint_for(code: str) -> str | None:
    return HINTS.get(code)


def is_retryable(code: str) -> bool:
    return code in RETRYABLE
