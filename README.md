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
