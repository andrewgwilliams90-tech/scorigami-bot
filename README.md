# Scorigami → Discord bot

Checks real NFL game results and posts to a Discord channel the moment a
final score happens that's **never occurred before in NFL history** — a
"Scorigami." Runs for free on GitHub Actions, no server, no social media
accounts to depend on.

## How it works

Instead of relying on a Twitter/X or Bluesky bot (both turned out to be
unreliable), this pulls directly from a free, actively-maintained public
dataset of every NFL game since 1999, which updates itself shortly after
each game ends. Every 15 minutes it checks for newly finished games and
compares each final score against all NFL history. If a score has never
happened before, it posts an alert.

## Setup (5 minutes, no coding required)

1. **Create a Discord webhook** for your target channel:
   - In Discord, go to the channel → Edit Channel → Integrations → Webhooks
     → New Webhook
   - Name it (e.g. "Scorigami") and copy the Webhook URL

2. **Add it as a secret in this repo:**
   - Go to your repo → Settings → Secrets and variables → Actions →
     New repository secret
   - Name: `DISCORD_WEBHOOK_URL`
   - Value: paste the webhook URL

3. **Turn on Actions:** go to the "Actions" tab and enable workflows if
   prompted.

4. **Test it:** Actions → "Check Scorigami" → "Run workflow" to trigger it
   manually. The first-ever run just sets a baseline (won't post anything
   old) — every run after that checks for new scorigamis.

## Notes

- By default it only posts when a **scorigami** happens. If you'd rather
  see every finished game reported (scorigami or not), open
  `scorigami_bot.py` and change `POST_EVERY_GAME = False` to `True`.
- No API keys, logins, or third-party accounts required — the data source
  is a public file, no auth needed.
- If your repo is private, GitHub Actions has a free monthly minutes quota
  (2,000 min/month) — running every 15 min comfortably fits within that.
  Public repos have unlimited Action minutes.
- If nothing posts, check the Actions tab for a failed run — it'll show
  the error (usually a missing/mistyped secret).
