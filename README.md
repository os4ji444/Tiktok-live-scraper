---
title: TikTok Live Finder
emoji: 🔴
colorFrom: red
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---

# TikTok Live Finder

Watches everyone a TikTok account **follows** and shows which of them are
**LIVE right now**.

Two ways to use it:

| | |
|---|---|
| **Dashboard** (recommended) | `dashboard.py` — web dashboard, runs in the background, open from your phone, cookie login, auto re-scans |
| **One-shot script** | `tiktok_live_finder.py` — single scan from the command line |

---

## Dashboard

### Start it

- Double-click **`start_dashboard.bat`** → runs hidden in the background
  (no window). Or run `python dashboard.py` to see the console.
- Open **http://localhost:8321** on the PC.
- On your **phone** (same Wi-Fi): open `http://<PC-IP>:8321` — the exact
  address is printed when the server starts (e.g. `http://192.168.1.5:8321`).

### Log in with cookies (needed to read Following lists)

1. On your PC browser, log in to **tiktok.com** normally.
2. Install the **Cookie-Editor** extension (Chrome/Edge/Firefox).
3. On tiktok.com, open Cookie-Editor → **Export → JSON** (copies to clipboard).
4. In the dashboard: **⚙ Settings** → paste into the cookies box → **Save**.

Cookies are stored only on your PC in `data/cookies.txt`.

### Use it

- Type a username → **Add**. Its full profile card appears (avatar, bio,
  verified badge, Following/Followers/Likes counts).
- Press **▶ Start** to scrape that account's complete Following list —
  a progress bar shows percent done, accounts processed, and time left,
  and live accounts appear in the grid the moment they are discovered.
- The background worker re-scans automatically (default every 5 min —
  change in Settings). **↻ Scan live** forces a scan right now.
- Live accounts show a pulsing dot, live viewer count, and a thumbnail —
  click the thumbnail for a preview popup, or **▶ Watch** to open the stream.
- **⬇ Excel** / **⬇ CSV** download `<account>_FollowingList_<date>.xlsx`/`.csv`
  with username, display name, counts, bio, live status + timestamp,
  Public/Private, and a clickable profile link per row (Excel has filters on
  and header row frozen).
- Set a **PIN** in Settings if other people can reach your dashboard.

### secUid (⚙ UID button) — for the full following list

The scraper pages through TikTok's own API by cursor, which needs the target
account's **secUid**. It's auto-detected from the profile, but if a scrape
comes back short you can set it manually:

1. Open **tiktok.com/@theaccount** in your browser.
2. Press **F12** → **Network** tab.
3. Scroll their Following list (or open it) so requests appear.
4. Click a request named **user/list** → find **secUid** in the query
   string / payload → copy its value (starts with `MS4wLjABAAAA…`).
5. In the dashboard, click **⚙ UID** on that account, paste it, **Save UID**,
   then press **▶ Start** again.

### Reaching it from outside your home (optional)

The dashboard only works on your Wi-Fi by default. To open it from anywhere,
run a tunnel on the PC, e.g. `cloudflared tunnel --url http://localhost:8321`
(gives you a public https link). Set a PIN first if you do this.

### Put it online for free (no PC needed)

**Option A — Hugging Face Spaces (free, NO credit card):**

1. Create a free account at [huggingface.co](https://huggingface.co/join)
   (email only, no card).
2. Go to **New Space** ([huggingface.co/new-space](https://huggingface.co/new-space)):
   pick any name (e.g. `tiktok-live-finder`), SDK = **Docker** → **Blank**,
   hardware = **CPU basic (free)**, visibility = **Public**, then **Create**.
3. In the new Space, open the **Files** tab → **+ Contribute → Upload files**,
   and upload these files from this repo (download them from GitHub first, or
   clone the repo):
   - `Dockerfile`, `dashboard.py`, `scraper.py`, `requirements.txt`,
     `README.md`, and the `templates` folder (with `index.html` inside).
   - **Do NOT upload the `data` folder** — a public Space's files are visible
     to everyone, and `data/` holds your cookies/token. Secrets go in step 4.
4. Open the Space's **Settings** → **Variables and secrets** → add two
   **secrets**:
   - `DASHBOARD_PIN` = a PIN of your choice (required — keeps strangers out)
   - `ED_TOKEN` = your EnsembleData API token
5. The Space builds automatically (~2 min). Your dashboard is then live at
   `https://<your-username>-<space-name>.hf.space` — open it from any phone,
   enter your PIN, add an account, press **▶ Start**.

Free Spaces only sleep after ~48 hours with no visitors (much friendlier than
Render's 15 minutes) and wake automatically on the next visit. The disk is
temporary: scraped lists survive normal use but reset when the Space restarts,
so press **▶ Start** again after a restart to re-scrape.

**Option B — Render (asks for a credit card in many countries):**

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/os4ji444/Tiktok-live-scraper)

1. Click the button above (create a free [Render](https://render.com) account
   and connect GitHub when asked).
2. When prompted, fill in the two environment variables:
   - **DASHBOARD_PIN** — a PIN of your choice; the online dashboard is public,
     so this is what keeps strangers out. **Do not leave it empty.**
   - **ED_TOKEN** — your EnsembleData API token (from
     dashboard.ensembledata.com), used to scrape following lists.
3. Press **Apply / Deploy**. After a couple of minutes your dashboard is live
   at `https://tiktok-live-finder-XXXX.onrender.com` — open it from any phone
   or PC, enter your PIN, and use it exactly like the local version.

Notes for the online version:

- It scrapes following lists through the EnsembleData API only (the
  off-screen-Chrome fallback needs a desktop and is disabled there), so the
  ED_TOKEN is required.
- Render's free tier **sleeps after ~15 min without visitors** — the first
  visit after a pause takes ~1 min to wake, and auto re-scans pause while it
  sleeps. Keeping the tab open keeps it awake.
- The free tier's disk is temporary: accounts you add and lists you scrape
  survive day-to-day use but reset when the service restarts or redeploys.
  Anything committed to the repo's `data/state.json` is restored on restart.

### Auto-start with Windows (optional)

Press `Win+R`, type `shell:startup`, press Enter, and copy a shortcut to
`start_dashboard.bat` into that folder.

---

## One-shot script

```
python tiktok_live_finder.py <username> --login    # first time: log in in the window
python tiktok_live_finder.py <username>            # scan
python tiktok_live_finder.py <username> --headless --max 300
```

Results are saved to `following_<user>.json` and `live_now_<user>.csv`.

---

## Notes & limits

- **A Chrome window opens (off-screen) during a scrape.** TikTok's bot
  detection cripples a hidden/headless browser (the page never finishes
  loading), so the following-list scrape drives a real Chrome window parked
  off-screen at position 3000,3000. You normally won't see it. Don't close
  it while a scrape is running. Live-status scans don't need it.
- TikTok only shows Following lists to **logged-in** users; private
  Following lists are only visible to the account owner.
- Live checks are throttled to stay polite. A 1,000-account list takes
  roughly 1–2 minutes per scan.
- TikTok changes its site often — if the following list stops loading,
  selectors in `tiktok_live_finder.py` may need updating.
- Requirements: Python 3.10+, `pip install flask requests playwright`,
  `playwright install chromium`.
