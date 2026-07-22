"""
TikTok Live Finder
==================
Given a TikTok username, this tool:
  1. Opens their profile in a real (automated) browser
  2. Opens the "Following" popup and scrolls it to the bottom to collect
     every followed account
  3. Checks each followed account and reports the ones that are LIVE right now
  4. Saves results to following_<user>.json and live_now_<user>.csv

Usage:
    python tiktok_live_finder.py <username>              # normal run
    python tiktok_live_finder.py <username> --login      # first run: log in manually
    python tiktok_live_finder.py <username> --headless   # run without a visible window
    python tiktok_live_finder.py <username> --max 500    # stop after N followings

Notes:
  - TikTok only shows the Following list if it is public, OR if you are
    logged in as the account owner. Run once with --login, sign in in the
    window that opens, then press Enter in this console. The session is
    saved in the ./tt_profile folder and reused on later runs.
  - Live status is checked through TikTok's own web endpoint
    (the same one tiktok.com uses), throttled to be polite.
"""

import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

BASE = "https://www.tiktok.com"
PROFILE_DIR = Path(__file__).parent / "tt_profile"   # persistent browser profile (keeps login)
LIVE_CHECK_DELAY = 1.2                               # seconds between live checks
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def log(msg: str) -> None:
    print(msg, flush=True)


def open_following_popup(page, username: str) -> bool:
    """Open the profile and click the Following counter. Returns True on success."""
    page.goto(f"{BASE}/@{username}", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3000)

    # Cookie banner, if any
    for sel in ("button:has-text('Decline optional cookies')",
                "button:has-text('Decline all')"):
        try:
            page.locator(sel).first.click(timeout=2000)
            break
        except Exception:
            pass

    if page.locator("text=Couldn't find this account").count():
        log(f"[!] Account @{username} not found.")
        return False

    logged_in = page.locator('[data-e2e="top-login-button"]').count() == 0

    # TikTok overlays banners that swallow clicks - remove them first
    page.evaluate("""() => {
        document.querySelector('#pns-communication-service')?.remove();
        document.querySelector('[id*="banner"]')?.remove();
    }""")

    try:
        page.locator('[data-e2e="following-count"]').first.click(timeout=10000, force=True)
    except PWTimeout:
        # fallback: any element whose text is exactly "Following" near the counters
        try:
            page.get_by_text("Following", exact=True).first.click(timeout=5000, force=True)
        except PWTimeout:
            log("[!] Could not find the Following counter on the profile page.")
            return False

    page.wait_for_timeout(2500)

    if page.locator("div[role='dialog']").count() == 0 and not logged_in:
        log("[!] You are not logged in - TikTok only shows Following lists to "
            "logged-in users.")
        log("    Run:  python tiktok_live_finder.py "
            f"{username} --login")
        log("    ...sign in in the browser window, press Enter, and it will continue.")
        return False

    # Make sure the "Following" tab inside the popup is selected (not "Followers")
    try:
        dialog = page.locator("div[role='dialog']").first
        dialog.get_by_text(re.compile(r"^Following", re.I)).first.click(timeout=3000)
        page.wait_for_timeout(1500)
    except Exception:
        pass

    if page.locator("text=/following list is (currently )?hidden|private/i").count():
        log("[!] This account's Following list is hidden. "
            "Run with --login and sign in as the account owner to see it.")
        return False
    return True


def collect_following(page, max_users: int | None) -> list[dict]:
    """Scroll the Following popup until no new users load; return the list."""
    dialog = page.locator("div[role='dialog']").first
    try:
        dialog.wait_for(state="visible", timeout=10000)
    except PWTimeout:
        log("[!] Following popup did not open.")
        return []

    if re.search(r"log in to tiktok", dialog.inner_text(), re.I):
        log("[!] TikTok is asking you to log in. Run again with --login first.")
        return []

    def grab() -> dict[str, str]:
        """Return {username: display_name} currently rendered in the popup."""
        users: dict[str, str] = {}
        for a in dialog.locator("a[href*='/@']").all():
            href = a.get_attribute("href") or ""
            m = re.match(r"^(?:https?://(?:www\.)?tiktok\.com)?/@([A-Za-z0-9._]+)", href)
            if not m:
                continue
            uname = m.group(1)
            if uname.lower() in ("", "live"):
                continue
            if uname not in users:
                users[uname] = (a.inner_text() or "").strip().split("\n")[0]
        return users

    seen: dict[str, str] = {}
    stagnant_rounds = 0
    while True:
        current = grab()
        seen.update(current)
        log(f"    collected {len(seen)} accounts...")

        if max_users and len(seen) >= max_users:
            break

        # Scroll the popup's inner scrollable area to the bottom
        page.evaluate("""() => {
            const dlg = document.querySelector("div[role='dialog']");
            if (!dlg) return;
            let target = null, best = -1;
            for (const el of dlg.querySelectorAll('*')) {
                if (el.scrollHeight > el.clientHeight + 50 && el.clientHeight > best) {
                    best = el.clientHeight; target = el;
                }
            }
            (target || dlg).scrollTop = (target || dlg).scrollHeight;
        }""")
        page.wait_for_timeout(1800)

        after = grab()
        if len(set(after) - set(seen)) == 0 and len(after) <= len(seen):
            stagnant_rounds += 1
        else:
            stagnant_rounds = 0
            seen.update(after)
        if stagnant_rounds >= 3:   # nothing new after 3 scrolls -> end of list
            break

    result = [{"username": u, "display_name": n} for u, n in seen.items()]
    return result[:max_users] if max_users else result


def check_live(page, username: str) -> dict:
    """
    Check live status via TikTok's own web API (uses the browser's cookies).
    status 2 = live, 4 = offline.
    """
    url = (f"{BASE}/api-live/user/room/?aid=1988&sourceType=54"
           f"&uniqueId={username}")
    try:
        resp = page.request.get(url, headers={"User-Agent": UA}, timeout=15000)
        data = resp.json()
        user = (data.get("data") or {}).get("user") or {}
        live_room = (data.get("data") or {}).get("liveRoom") or {}
        status = user.get("status")
        is_live = status == 2
        return {
            "username": username,
            "live": is_live,
            "room_id": user.get("roomId") or "",
            "title": (live_room.get("title") or "").strip(),
            "viewers": live_room.get("liveRoomStats", {}).get("userCount", ""),
            "url": f"{BASE}/@{username}/live" if is_live else "",
        }
    except Exception as e:
        return {"username": username, "live": False, "error": str(e)[:120],
                "room_id": "", "title": "", "viewers": "", "url": ""}


def main() -> None:
    ap = argparse.ArgumentParser(description="Find which accounts a TikTok user follows are live now.")
    ap.add_argument("username", help="TikTok username (with or without @)")
    ap.add_argument("--login", action="store_true",
                    help="Open a browser to log in first (needed for hidden following lists)")
    ap.add_argument("--headless", action="store_true", help="Run without a visible browser window")
    ap.add_argument("--max", type=int, default=None, help="Stop after collecting N followings")
    args = ap.parse_args()

    username = args.username.lstrip("@").strip()
    out_json = Path(__file__).parent / f"following_{username}.json"
    out_csv = Path(__file__).parent / f"live_now_{username}.csv"

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(PROFILE_DIR),
            headless=args.headless and not args.login,
            user_agent=UA,
            viewport={"width": 1280, "height": 850},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        if args.login:
            page.goto(f"{BASE}/login", wait_until="domcontentloaded")
            input(">>> Log in to TikTok in the browser window, then press Enter here... ")

        log(f"[1/3] Opening @{username}'s profile and Following list...")
        if not open_following_popup(page, username):
            ctx.close()
            sys.exit(1)

        log("[2/3] Scrolling the Following list (this can take a while)...")
        following = collect_following(page, args.max)
        if not following:
            log("[!] No followings collected. The list may be empty or hidden.")
            ctx.close()
            sys.exit(1)

        out_json.write_text(json.dumps(following, indent=2, ensure_ascii=False), encoding="utf-8")
        log(f"    -> {len(following)} accounts saved to {out_json.name}")

        # Close popup before making API calls
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass

        log(f"[3/3] Checking live status of {len(following)} accounts...")
        live_now: list[dict] = []
        for i, f in enumerate(following, 1):
            r = check_live(page, f["username"])
            r["display_name"] = f["display_name"]
            mark = "LIVE " if r["live"] else "     "
            log(f"    [{i}/{len(following)}] {mark}@{f['username']}"
                + (f"  ({r['viewers']} viewers)" if r["live"] and r["viewers"] else ""))
            if r["live"]:
                live_now.append(r)
            time.sleep(LIVE_CHECK_DELAY)

        ctx.close()

    print("\n" + "=" * 60)
    if live_now:
        print(f"  {len(live_now)} account(s) LIVE right now:\n")
        for r in live_now:
            print(f"   @{r['username']}  ({r['display_name']})")
            if r["title"]:
                print(f"      title:   {r['title']}")
            if r["viewers"]:
                print(f"      viewers: {r['viewers']}")
            print(f"      watch:   {r['url']}\n")
    else:
        print("  Nobody in the following list is live right now.")
    print("=" * 60)

    with out_csv.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["username", "display_name", "title",
                                           "viewers", "url", "room_id"])
        w.writeheader()
        for r in live_now:
            w.writerow({k: r.get(k, "") for k in w.fieldnames})
    print(f"\nLive accounts saved to {out_csv.name}")


if __name__ == "__main__":
    main()
