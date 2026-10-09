"""
Scorigami checker -> Discord bridge.

Two data sources:
1. nflverse's public "schedules" dataset -> tells us which games just
   finished (reliable, versioned, built for programmatic access).
2. The official nflscorigami.com site's own data endpoint -> gives us the
   REAL historical count and "first ever happened on" date for every score
   combination, going back to 1920 (same source the official site itself
   uses), so our scorigami count matches theirs.

Source #2 is an unofficial/undocumented endpoint (just what their website
happens to call), so if it's ever unreachable, the bot falls back to
reporting scores without the official tally rather than failing outright.

Required environment variable:
  DISCORD_WEBHOOK_URL  Discord channel webhook URL

State is kept in state.json (the most recent game date we've already
checked, plus which game IDs on that date we've handled) so the same game
never gets reported twice even if a Sunday slate finishes across multiple
runs. The GitHub Actions workflow commits this file back to the repo after
every run.
"""

import csv
import gzip
import io
import json
import os
import sys
from pathlib import Path

import requests

STATE_FILE = Path(__file__).parent / "state.json"
GAMES_CSV_URL = "https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv.gz"
OFFICIAL_DATA_URL = "https://nflscorigami.com/data"

# Set to True if you want every finished game reported, not just scorigamis.
POST_EVERY_GAME = True


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"last_date": None, "last_date_game_ids": []}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2))


def fetch_games() -> list[dict]:
    resp = requests.get(GAMES_CSV_URL, timeout=30)
    resp.raise_for_status()
    text = gzip.decompress(resp.content).decode("utf-8")
    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


def fetch_official_matrix():
    """Returns the official site's matrix, or None if it's unreachable."""
    try:
        resp = requests.get(OFFICIAL_DATA_URL, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        return data.get("matrix")
    except Exception as e:
        print(f"Warning: couldn't reach official scorigami data ({e}). "
              f"Falling back to plain score reporting.", file=sys.stderr)
        return None


def _cell(matrix, loser_score: int, winner_score: int):
    """Safely get matrix[loser][winner]. Works whether the official data
    arrives as lists (what it actually is) or as dicts keyed by score."""
    try:
        row = matrix[loser_score] if isinstance(matrix, list) else matrix.get(str(loser_score))
        if not row:
            return None
        cell = row[winner_score] if isinstance(row, list) else row.get(str(winner_score))
        return cell if cell else None
    except (IndexError, KeyError, TypeError):
        return None


def lookup_official(matrix, loser_score: int, winner_score: int) -> dict | None:
    """Official matrix is indexed [loser_score][winner_score] -> {count, first_date, last_date}."""
    if matrix is None:
        return None
    return _cell(matrix, loser_score, winner_score)


def _all_cells(matrix):
    rows = matrix if isinstance(matrix, list) else list(matrix.values())
    for row in rows:
        if not row:
            continue
        cells = row if isinstance(row, list) else list(row.values())
        for cell in cells:
            if cell and cell.get("count", 0) > 0:
                yield cell


def official_rank(matrix, as_of_date: str, already_counted: bool) -> int:
    """How many unique scores had their first-ever occurrence on or before
    as_of_date, i.e. 'this is the Nth unique score in NFL history.'
    If the official site hasn't added today's game yet, we add 1 for it.
    Ties on the exact same date are counted together, so this is a close
    approximation of the website's running order within a single day."""
    n = sum(1 for c in _all_cells(matrix) if str(c.get("first_date", ""))[:10] <= as_of_date)
    return n if already_counted else n + 1


def score_key(score_a: int, score_b: int) -> tuple:
    return tuple(sorted((score_a, score_b)))


def send_to_discord(webhook_url: str, message: str) -> None:
    resp = requests.post(webhook_url, json={"content": message}, timeout=15)
    resp.raise_for_status()


def main() -> None:
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        print("Missing DISCORD_WEBHOOK_URL env var.", file=sys.stderr)
        sys.exit(1)

    state = load_state()
    last_date = state.get("last_date")
    last_date_game_ids = set(state.get("last_date_game_ids", []))

    games = fetch_games()
    official_matrix = fetch_official_matrix()

    completed = [g for g in games if g["home_score"] not in ("", None)]
    completed.sort(key=lambda g: (g["gameday"], g["game_id"]))

    if last_date is None:
        if completed:
            newest_date = completed[-1]["gameday"]
            ids_on_newest_date = {g["game_id"] for g in completed if g["gameday"] == newest_date}
            state["last_date"] = newest_date
            state["last_date_game_ids"] = sorted(ids_on_newest_date)
            save_state(state)
        print("First run: baseline set, no messages sent.")
        return

    # Always compute our own backup counts from nflverse (reliable, but only
    # goes back to 1999), in case the official site is unreachable this run.
    backup_counts: dict = {}
    newly_finished = []
    for game in completed:
        key = score_key(int(float(game["home_score"])), int(float(game["away_score"])))
        backup_counts[key] = backup_counts.get(key, 0) + 1

        gameday = game["gameday"]
        is_new = (gameday > last_date) or (
            gameday == last_date and game["game_id"] not in last_date_game_ids
        )
        if is_new:
            newly_finished.append((game, backup_counts[key]))

    if not newly_finished:
        print("No newly finished games.")
        return

    for game, backup_count in newly_finished:
        home, home_score, away, away_score = (
            game["home_team"], int(float(game["home_score"])),
            game["away_team"], int(float(game["away_score"])),
        )
        winner_score, loser_score = max(home_score, away_score), min(home_score, away_score)
        gameday = game["gameday"]

        official = lookup_official(official_matrix, loser_score, winner_score)

        if official_matrix is not None:
            # Trust the official site when we successfully reached it.
            already_counted = bool(
                official and official.get("count", 0) == 1
                and str(official.get("first_date", ""))[:10] == gameday
            )
            is_scorigami = official is None or official.get("count", 0) == 0 or already_counted
            count = official["count"] if official else 0
            source_note = ""
        else:
            # Official site unreachable this run - fall back to our own
            # count since 1999 so we don't falsely call everything new.
            is_scorigami = backup_count == 1
            count = backup_count
            source_note = " (backup count since 1999 — official site was unreachable this run)"

        if is_scorigami:
            rank_note = ""
            if official_matrix is not None:
                rank = official_rank(official_matrix, gameday, already_counted)
                rank_note = f" This is the **{rank}th unique score** in NFL history."
            message = (
                f"🚨 **SCORIGAMI!** 🚨\n"
                f"{away} {away_score} — {home} {home_score} ({gameday})\n"
                f"This is the first time this score has ever happened.{rank_note}{source_note}"
            )
            send_to_discord(webhook_url, message)
            print(f"Posted SCORIGAMI: {away} {away_score} - {home} {home_score}")
        elif POST_EVERY_GAME:
            message = (
                f"{away} {away_score} — {home} {home_score} ({gameday})\n"
                f"No scorigami — this score has now happened {count} times.{source_note}"
            )
            send_to_discord(webhook_url, message)
            print(f"Posted (non-scorigami): {away} {away_score} - {home} {home_score}")
        else:
            print(f"Checked, not a scorigami: {away} {away_score} - {home} {home_score}")

    newest_date = completed[-1]["gameday"]
    ids_on_newest_date = {g["game_id"] for g in completed if g["gameday"] == newest_date}
    state["last_date"] = newest_date
    state["last_date_game_ids"] = sorted(ids_on_newest_date)
    save_state(state)


if __name__ == "__main__":
    main()
