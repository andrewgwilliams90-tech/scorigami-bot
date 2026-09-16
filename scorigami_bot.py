"""
Scorigami checker -> Discord bridge.

Computes Scorigami directly from real NFL game data instead of depending on
any third-party bot or social account. Data source: the nflverse project's
public, auto-updated "schedules" dataset, which has the final score of
every NFL game back to 1999 and refreshes shortly after each game ends.
No API key or login needed to read it.

Required environment variable:
  DISCORD_WEBHOOK_URL  Discord channel webhook URL

State is kept in state.json (the most recent game date we've already
checked, plus which game IDs on that date we've handled) so the same game
never gets reported twice even if a Sunday slate finishes across multiple
runs. The GitHub Actions workflow commits this file back to the repo after
every run.
"""

import csv
import io
import json
import os
import sys
from pathlib import Path

import requests

STATE_FILE = Path(__file__).parent / "state.json"
GAMES_CSV_URL = "https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv"

# Set to True if you want every finished game reported, not just scorigamis.
POST_EVERY_GAME = False


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"last_date": None, "last_date_game_ids": []}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2))


def fetch_games() -> list[dict]:
    resp = requests.get(GAMES_CSV_URL, timeout=30)
    resp.raise_for_status()
    reader = csv.DictReader(io.StringIO(resp.text))
    return list(reader)


def score_key(score_a: int, score_b: int) -> tuple:
    # Order-independent so 24-17 and 17-24 count as the same combination.
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

    # Only games that have actually finished (have a score) count as history.
    completed = [g for g in games if g["home_score"] not in ("", None)]
    completed.sort(key=lambda g: (g["gameday"], g["game_id"]))

    if last_date is None:
        # First-ever run: set today's data as the baseline so we don't
        # dump 25+ years of scorigami history into the channel at once.
        if completed:
            newest_date = completed[-1]["gameday"]
            ids_on_newest_date = {g["game_id"] for g in completed if g["gameday"] == newest_date}
            state["last_date"] = newest_date
            state["last_date_game_ids"] = sorted(ids_on_newest_date)
            save_state(state)
        print("First run: baseline set, no messages sent.")
        return

    # Walk history in order, tracking how many times each score combo has
    # occurred so far, so we can tell whether a NEW game is a first-ever score.
    seen_counts: dict = {}
    newly_finished = []

    for game in completed:
        gameday = game["gameday"]
        is_new = (gameday > last_date) or (
            gameday == last_date and game["game_id"] not in last_date_game_ids
        )

        key = score_key(int(float(game["home_score"])), int(float(game["away_score"])))
        seen_counts[key] = seen_counts.get(key, 0) + 1

        if is_new:
            newly_finished.append((game, seen_counts[key]))

    if not newly_finished:
        print("No newly finished games.")
        return

    for game, occurrences in newly_finished:
        home, home_score, away, away_score = (
            game["home_team"], game["home_score"], game["away_team"], game["away_score"]
        )

        if occurrences == 1:
            message = (
                f"🚨 **SCORIGAMI!** 🚨\n"
                f"{away} {away_score} — {home} {home_score} ({game['gameday']})\n"
                f"This is the first time in NFL history this score has happened."
            )
            send_to_discord(webhook_url, message)
            print(f"Posted SCORIGAMI: {away} {away_score} - {home} {home_score}")
        elif POST_EVERY_GAME:
            message = (
                f"{away} {away_score} — {home} {home_score} ({game['gameday']})\n"
                f"No scorigami — this score has now happened {occurrences} times."
            )
            send_to_discord(webhook_url, message)
            print(f"Posted (non-scorigami): {away} {away_score} - {home} {home_score}")
        else:
            print(f"Checked, not a scorigami ({occurrences}x): {away} {away_score} - {home} {home_score}")

    newest_date = completed[-1]["gameday"]
    ids_on_newest_date = {g["game_id"] for g in completed if g["gameday"] == newest_date}
    state["last_date"] = newest_date
    state["last_date_game_ids"] = sorted(ids_on_newest_date)
    save_state(state)


if __name__ == "__main__":
    main()
