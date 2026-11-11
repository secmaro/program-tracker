# Program Tracker 🤖

A Telegram bot that monitors **Bugcrowd** for new bug bounty programs and scope
changes. Cloud-hosted on Render free tier — your PC stays off. Sends you a
Telegram alert the moment a new program appears or an existing program adds
new in-scope assets.

Built to pair with the bug-reaper skill in ZCode: when an alert fires, you
paste the program URL straight into ZCode and start hunting.

---

## What you get

- **New program alerts** — within ~15 min of a Bugcrowd program going public
- **Scope change alerts** — when a program adds new domains/endpoints
- **Alert format**: program name + direct URL + scope summary (inlined)
- **State persistence** via GitHub Gist (survives Render deploys)
- **No filtering** — you see every new Bugcrowd program (by design)

## Alert examples

**New program:**
```
🆕 NEW PROGRAM
━━━━━━━━━━━━━━━━
Name: Acme Corp Bug Bounty
URL: https://bugcrowd.com/acme
Scope (12 assets):
  • acme.com
  • api.acme.com
  • app.acme.com
  • ...(+9 more)
━━━━━━━━━━━━━━━━
```

**Scope change:**
```
🔄 SCOPE CHANGE
━━━━━━━━━━━━━━━━
Program: Acme Corp Bug Bounty
URL: https://bugcrowd.com/acme
+ Added (3):
  • new.acme.com
  • staging.acme.com
  • admin.acme.com
- Removed (1):
  • old.acme.com
━━━━━━━━━━━━━━━━
```

---

## Architecture

| Component | Choice | Why |
|---|---|---|
| Data source | ProjectDiscovery `public-bugbounty-programs` JSON | Bugcrowd's site is JS-rendered; this is a community-maintained JSON, updated daily, with all programs across platforms. Filter to `bugcrowd` only. |
| State storage | GitHub Gist via GitHub API | Render free tier has ephemeral filesystem (wiped on deploy). Gist is free + persistent. |
| Scheduler | APScheduler inside FastAPI | Runs every 15 min, no external cron needed. |
| Hosting | Render free web service + UptimeRobot ping | UptimeRobot pings `/health` every 10 min → prevents Render spin-down. |
| Alerts | Telegram Bot API (MarkdownV2) | Direct to your phone. |

---

## Setup — step by step

### Step 1: Create the Telegram bot

1. Open Telegram, message [@BotFather](https://t.me/BotFather)
2. Send `/newbot` → pick a name (e.g. `Program Tracker`) and a username ending in `bot` (e.g. `acme_program_tracker_bot`)
3. BotFather gives you a **bot token** like `1234567890:ABCdefGHI...` — save it
4. Create a **private channel** (or use your own chat):
   - For a channel: create it, add your bot as admin, then forward a message from the channel to [@userinfobot](https://t.me/userinfobot) to get the **chat ID** (starts with `-100...`)
   - For your own chat: just message [@userinfobot](https://t.me/userinfobot) directly — your chat ID is the response (positive number)

### Step 2: Create a GitHub token for Gist storage

1. Go to https://github.com/settings/tokens?type=beta (fine-grained tokens — safer)
2. Click **Generate new token**
3. Set:
   - Name: `program-tracker`
   - Expiration: 90 days (or 1 year)
   - Repository access: **No repository access** (we only need gist)
   - Permissions → Account permissions → **Gists → Read and write**
4. Generate → copy the token (`github_pat_...`)

### Step 3: Deploy to Render

1. Push this folder to a GitHub repo (private is fine)
2. Go to https://dashboard.render.com → **New +** → **Blueprint**
3. Select your repo — Render reads `render.yaml` automatically
4. Fill in the env vars (Render prompts for each):
   - `TELEGRAM_BOT_TOKEN` — from step 1
   - `TELEGRAM_CHAT_ID` — from step 1
   - `GITHUB_TOKEN` — from step 2
   - `GIST_ID` — **leave blank** (bot creates it on first run)
   - `CHECK_INTERVAL_MINUTES` — `15` (default)
5. Click **Apply** — Render builds and deploys

### Step 4: Get your Gist ID back

On first run (within ~1 min of deploy), the bot will:
- Fetch all current Bugcrowd programs
- Save them as a baseline state in a new GitHub Gist
- Send you a Telegram message that looks like:

```
✅ Program Tracker started
━━━━━━━━━━━━━━━━
State gist: abc123def456...
Tracking: 312 Bugcrowd programs
Check interval: every 15 min
━━━━━━━━━━━━━━━━
Save the gist ID above as GIST_ID env var
so state persists across restarts.
```

**Important**: copy that gist ID, go back to Render → Environment → set `GIST_ID` to that value → save. This makes state survive future redeploys.

### Step 5: Keep Render awake (free tier spins down after 15 min idle)

1. Go to https://uptimerobot.com → sign up (free)
2. Add a new monitor:
   - Monitor type: **HTTP(s)**
   - Friendly name: `program-tracker`
   - URL: `https://your-app-name.onrender.com/health` (replace with your Render URL)
   - Monitoring interval: **10 minutes**
3. Save — UptimeRobot pings `/health` every 10 min, which keeps Render's free tier awake

That's it. The bot now runs 24/7 on Render's infra, alerting you in Telegram whenever a new Bugcrowd program appears or a scope changes.

---

## Files in this repo

| File | Purpose |
|---|---|
| `bot.py` | FastAPI server + APScheduler. Entry point. |
| `scraper.py` | Fetches Bugcrowd programs from ProjectDiscovery JSON. |
| `state.py` | GitHub Gist state storage + diff logic. |
| `notifier.py` | Telegram message formatting + send. |
| `config.py` | Env-based config. |
| `models.py` | Program + ProgramDiff dataclasses. |
| `requirements.txt` | Python deps. |
| `render.yaml` | Render Blueprint config. |
| `.env.example` | Template for local dev env vars. |

---

## Local development (optional)

```bash
# 1. Set up venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Copy env template
cp .env.example .env
# Edit .env with your tokens

# 3. Run
export $(grep -v '^#' .env | xargs) && python bot.py
```

Visit `http://localhost:8000/health` — you should see `{"status": "ok", ...}`.

For the very first local run, the bot will create a Gist under your GitHub
account. Print it from the startup Telegram message and add `GIST_ID=...`
to your `.env`.

---

## Troubleshooting

**Bot deployed but no alerts / no startup message**
- Check Render logs: Dashboard → your service → Logs
- Verify `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are set correctly
- Send a test message manually: `curl "https://api.telegram.org/bot<TOKEN>/sendMessage" -d chat_id=<CHAT_ID> -d text=test`

**Startup message arrives but state gist is empty on next deploy**
- You forgot to set `GIST_ID` after the first run. Find the gist ID in your GitHub gists (https://gist.github.com) or in the first Telegram message, then set it as `GIST_ID` env var in Render and redeploy.

**Render spins down and bot misses alerts**
- UptimeRobot isn't pinging. Verify the monitor URL is `https://<your-app>.onrender.com/health` and the interval is 10 min.
- Free Render tier can still drift by a few minutes; for tighter coverage upgrade to Render Starter ($7/mo) — eliminates spin-down entirely.

**ProjectDiscovery data doesn't show a program I see on Bugcrowd**
- Their JSON updates ~daily. New programs may take a few hours to appear. For faster coverage, add HackerOne monitoring in a future iteration (see `scraper.py`).

**Want to also monitor HackerOne / Intigriti / YesWeHack?**
- The data source already includes them — just remove the `bugcrowd.com` filter in `scraper.py:fetch_programs()` (around line 50). The rest of the bot works as-is.

---

## Cost

- **Render free tier**: $0/month (with UptimeRobot keep-alive)
- **UptimeRobot free**: $0/month (50 monitors, 10-min intervals)
- **GitHub Gist**: $0 (free, unlimited secret gists)
- **Telegram Bot API**: $0 (free for bots)
- **ProjectDiscovery JSON**: $0 (open source)

**Total: $0/month.** PC stays off. Bot runs forever.

---

## License

MIT — do whatever you want, no warranty.
