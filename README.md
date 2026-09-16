# Scorigami → Discord bot

Watches a Bluesky account (the Scorigami tracker) and posts any new post to a
Discord channel via webhook. Runs for free on GitHub Actions — no server,
no Yahoo/X credentials, nothing to keep running on your own machine.

## Setup (10 minutes, no coding required)

1. **Create a GitHub account** if you don't have one (free) — github.com.

2. **Create a new repository** and upload these files to it (drag-and-drop
   works fine on github.com, or use "Add file → Upload files").

3. **Find the Bluesky handle** for the Scorigami tracker: open the Bluesky
   app or bsky.app, search "Scorigami", and copy the handle from their
   profile URL (it'll look like `bsky.app/profile/<handle>`). Use just the
   handle part, not the full URL.

4. **Create a Discord webhook** for your target channel:
   - In Discord, go to the channel → Edit Channel → Integrations → Webhooks
     → New Webhook
   - Name it (e.g. "Scorigami") and copy the Webhook URL

5. **Add two secrets to your GitHub repo:**
   - Go to your repo → Settings → Secrets and variables → Actions →
     New repository secret
   - Add `BSKY_HANDLE` = the handle from step 3
   - Add `DISCORD_WEBHOOK_URL` = the URL from step 4

6. **Turn on Actions:** go to the "Actions" tab in your repo and enable
   workflows if prompted. The bot will now run automatically every 15
   minutes.

7. **Test it:** go to Actions → "Check Scorigami" → "Run workflow" to
   trigger it manually and confirm it runs without errors. The very first
   run just sets a baseline (it won't post anything old) — every run after
   that will post new items as they appear.

## Notes

- This is a **public** Bluesky feed — no login or API key needed to read it.
- If your repo is private, GitHub Actions has a free monthly minutes quota
  (2,000 min/month on free plans) — running every 15 min comfortably fits
  within that. If you want to be extra safe, make the repo public (Actions
  are unlimited for public repos) or narrow the cron schedule to Sundays
  during football season.
- If Discord ever shows nothing posting, check the Actions tab for a failed
  run — it'll show you the error (usually a missing/mistyped secret).
