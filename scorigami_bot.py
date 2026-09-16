"""
Scorigami -> Discord bridge.

Polls a Bluesky account's public post feed (no auth required) and forwards
any new posts to a Discord channel via webhook.

Required environment variables:
  BSKY_HANDLE          e.g. "scorigami.bsky.social" (no @, no https://)
  DISCORD_WEBHOOK_URL  Discord channel webhook URL

State is kept in state.json (the last post URI we've already sent) so the
same post never gets forwarded twice. The GitHub Actions workflow commits
this file back to the repo after every run.
"""

import json
import os
import sys
from pathlib import Path

import requests

STATE_FILE = Path(__file__).parent / "state.json"
BSKY_FEED_URL = "https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed"


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"last_uri": None}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2))


def fetch_recent_posts(handle: str, limit: int = 10) -> list[dict]:
    resp = requests.get(
        BSKY_FEED_URL,
        params={"actor": handle, "limit": limit},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("feed", [])


def post_uri_to_web_url(handle: str, uri: str) -> str:
    # uri looks like: at://did:plc:xxxx/app.bsky.feed.post/<rkey>
    rkey = uri.rstrip("/").split("/")[-1]
    return f"https://bsky.app/profile/{handle}/post/{rkey}"


def send_to_discord(webhook_url: str, text: str, link: str) -> None:
    payload = {
        "username": "Scorigami",
        "embeds": [
            {
                "description": text[:4000],
                "url": link,
                "color": 0x00A8E8,
            }
        ],
    }
    resp = requests.post(webhook_url, json=payload, timeout=15)
    resp.raise_for_status()


def main() -> None:
    handle = os.environ.get("BSKY_HANDLE")
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")

    if not handle or not webhook_url:
        print("Missing BSKY_HANDLE or DISCORD_WEBHOOK_URL env vars.", file=sys.stderr)
        sys.exit(1)

    state = load_state()
    last_uri = state.get("last_uri")

    feed = fetch_recent_posts(handle)
    if not feed:
        print("No posts returned from Bluesky.")
        return

    # feed[0] is the newest post. Walk until we hit the last one we've seen.
    new_items = []
    for item in feed:
        uri = item["post"]["uri"]
        if uri == last_uri:
            break
        new_items.append(item)

    if last_uri is None:
        # First-ever run: don't spam the channel with backlog, just
        # record the current newest post as the baseline.
        state["last_uri"] = feed[0]["post"]["uri"]
        save_state(state)
        print("First run: baseline set, no messages sent.")
        return

    if not new_items:
        print("No new posts.")
        return

    # Post oldest-first so the channel reads in chronological order.
    for item in reversed(new_items):
        post = item["post"]
        text = post["record"].get("text", "")
        link = post_uri_to_web_url(handle, post["uri"])
        send_to_discord(webhook_url, text, link)
        print(f"Posted: {text[:60]!r}")

    state["last_uri"] = feed[0]["post"]["uri"]
    save_state(state)


if __name__ == "__main__":
    main()
