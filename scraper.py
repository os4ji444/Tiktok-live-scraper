"""
TikTok scraping helpers for the Live Finder dashboard.

- fetch_profile(username)    -> rich profile info (no login needed for public)
- scrape_following(...)      -> full following list with per-account details,
                                streaming progress through a callback
- check_live(username, ...)  -> live status + viewers + cover thumbnail
"""

import json
import re
import time

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

ED_ROOT = "https://ensembledata.com/apis"


# ---------------------------------------------- EnsembleData (mobile API) ----

def _ed_avatar(u: dict) -> str:
    a = u.get("avatar_thumb") or u.get("avatarThumb") or u.get("avatar_larger")
    if isinstance(a, dict):
        ul = a.get("url_list") or []
        return ul[0] if ul else ""
    return a or ""


def _entry_from_ed(item: dict) -> dict | None:
    """Normalize one EnsembleData following record (mobile snake_case or web)."""
    if not isinstance(item, dict):
        return None
    u = item.get("user") if isinstance(item.get("user"), dict) else item
    uid = u.get("unique_id") or u.get("uniqueId")
    if not uid:
        return None
    st = item.get("stats") or u.get("stats") or {}
    return {
        "username": uid,
        "display_name": u.get("nickname") or "",
        "bio": u.get("signature") or "",
        "verified": bool(u.get("verified") or u.get("custom_verify")
                         or u.get("enterprise_verify_reason")),
        "private": bool(u.get("secret") or u.get("private_account")
                        or u.get("privateAccount")),
        "avatar": _ed_avatar(u),
        "followers": u.get("follower_count") or st.get("followerCount") or 0,
        "following": u.get("following_count") or st.get("followingCount") or 0,
        "likes": u.get("total_favorited") or u.get("heart_count")
                 or st.get("heartCount") or 0,
    }


def ed_resolve_id(secuid: str, token: str, log=print) -> str:
    """Get the numeric user id for a secUid via EnsembleData."""
    try:
        r = requests.get(ED_ROOT + "/tt/user/info-from-secuid",
                         params={"secUid": secuid, "token": token}, timeout=30)
        j = r.json()
        d = j.get("data") or {}
        u = d.get("user") if isinstance(d.get("user"), dict) else d
        return str(u.get("id") or u.get("uid") or u.get("uid_str") or "")
    except Exception as e:
        log(f"could not resolve user id: {str(e)[:80]}")
        return ""


def scrape_following_ed(secuid: str, token: str, ingest, log,
                        user_id: str = "", start_cursor=0, start_page_token="",
                        out: dict = None) -> tuple[bool, str]:
    """
    Pull the FULL following list of any account via EnsembleData's TikTok API
    (which uses TikTok's mobile backend - no ~150 web cap, works for accounts
    you don't own). Paginates with cursor + page_token until exhausted.
    Resumes from start_cursor/start_page_token and writes the stop position to
    `out` so a later run can continue. Returns (ok, error_message).
    """
    def finish(cur, tok, more, err):
        if out is not None:
            out["ed_cursor"], out["ed_page_token"] = cur, tok
            out["ed_more"] = more
        return got_any, err

    if not token:
        return False, "no EnsembleData API token set (add it in Settings)"
    if not secuid:
        return False, "no secUid - paste it in the account's UID field"
    if not user_id:
        user_id = ed_resolve_id(secuid, token, log)

    s = requests.Session()
    cursor = start_cursor if start_cursor not in (None, "") else 0
    page_token = start_page_token or ""
    got_any = False
    total = 0
    if cursor not in (0, "0", "") or page_token:
        log(f"  data-API: resuming from cursor {cursor!r}")
    for pg in range(4000):                     # safety ceiling
        try:
            r = s.get(ED_ROOT + "/tt/user/followings",
                     params={"id": user_id, "secUid": secuid, "cursor": cursor,
                             "page_token": page_token, "token": token},
                     timeout=45)
        except Exception as e:
            return finish(cursor, page_token, True,
                          f"stopped at {total}: request error: {str(e)[:80]}")
        if r.status_code in (401, 403, 491):
            return finish(cursor, page_token, True,
                          "EnsembleData token invalid - sign up at "
                          "dashboard.ensembledata.com and paste your token")
        if r.status_code in (429, 492, 493):
            return finish(cursor, page_token, True,
                          f"stopped at {total}: EnsembleData units/quota ran out "
                          f"(HTTP {r.status_code}) - the list is longer; top up "
                          f"units and press Start again to resume")
        if r.status_code != 200:
            return finish(cursor, page_token, True,
                          f"stopped at {total}: EnsembleData HTTP "
                          f"{r.status_code}: {r.text[:100]}")
        try:
            j = r.json()
        except Exception:
            return finish(cursor, page_token, True,
                          f"stopped at {total}: bad JSON: {r.text[:100]}")
        data = j.get("data") or {}
        lst = (data.get("followings") or data.get("users")
               or data.get("followers") or [])
        if not isinstance(lst, list):
            return finish(cursor, page_token, False,
                          f"unexpected response shape: {str(data)[:120]}")
        added = 0
        for it in lst:
            e = _entry_from_ed(it)
            if e:
                ingest(e)
                added += 1
        total += added
        got_any = got_any or added > 0
        cursor = data.get("nextCursor")
        if cursor is None:
            cursor = data.get("next_cursor")
        page_token = data.get("nextPageToken") or data.get("next_page_token") or ""
        if pg % 5 == 0 or not lst:
            log(f"  data-API page {pg + 1}: +{added} (total {total}) | "
                f"nextCursor={cursor!r} pageToken={'yes' if page_token else 'no'}")
        if not lst:
            return finish(cursor, page_token, False, "")   # true end
        if (cursor in (None, "", 0, "0")) and not page_token:
            log(f"  data-API: no next cursor/token after {total} - list ended")
            return finish(cursor, page_token, False, "")
        time.sleep(0.4)
    return finish(cursor, page_token, True, "")


# ------------------------------------------------------------- profiles ----

def fetch_profile(username: str, cookies: dict | None = None) -> dict | None:
    """Parse profile info out of the profile page's embedded JSON."""
    try:
        s = requests.Session()
        s.headers["User-Agent"] = UA
        for k, v in (cookies or {}).items():
            s.cookies.set(k, v, domain=".tiktok.com")
        r = s.get(f"https://www.tiktok.com/@{username}", timeout=20)
        m = re.search(r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" '
                      r'type="application/json">(.*?)</script>', r.text, re.S)
        if not m:
            return None
        scope = json.loads(m.group(1)).get("__DEFAULT_SCOPE__", {})
        ui = (scope.get("webapp.user-detail") or {}).get("userInfo") or {}
        u, st = ui.get("user") or {}, ui.get("stats") or {}
        if not u.get("uniqueId"):
            return None
        return {
            "username": u.get("uniqueId"),
            "nickname": u.get("nickname") or "",
            "bio": u.get("signature") or "",
            "verified": bool(u.get("verified")),
            "private": bool(u.get("privateAccount") or u.get("secret")),
            "avatar": u.get("avatarLarger") or u.get("avatarMedium") or "",
            "secuid": u.get("secUid") or "",
            "followers": st.get("followerCount") or 0,
            "following": st.get("followingCount") or 0,
            "likes": st.get("heartCount") or 0,
            "videos": st.get("videoCount") or 0,
            "fetched_at": int(time.time()),
        }
    except Exception:
        return None


# ------------------------------------------------------------ live check ----

def check_live(username: str, session: requests.Session) -> dict:
    """
    status 2 = live, 4 = offline (TikTok's own web endpoint).
    Returns "ok": False when the check couldn't be determined (empty body /
    rate-limited / error) so the caller can keep the previous status instead of
    wrongly marking the account offline.
    """
    url = (f"https://www.tiktok.com/api-live/user/room/"
           f"?aid=1988&sourceType=54&uniqueId={username}")
    try:
        d = session.get(url, timeout=15).json()
        user = (d.get("data") or {}).get("user") or {}
        room = (d.get("data") or {}).get("liveRoom") or {}
        status = user.get("status")
        if status not in (2, 4):              # unknown -> not a real answer
            return {"username": username, "ok": False, "live": False,
                    "checked_at": int(time.time())}
        return {
            "username": username,
            "ok": True,
            "live": status == 2,
            "title": (room.get("title") or "").strip(),
            "viewers": (room.get("liveRoomStats") or {}).get("userCount", 0) or 0,
            "avatar": user.get("avatarThumb") or "",
            "cover": room.get("coverUrl") or "",
            "url": f"https://www.tiktok.com/@{username}/live",
            "checked_at": int(time.time()),
        }
    except Exception:
        return {"username": username, "ok": False, "live": False,
                "checked_at": int(time.time())}


# ------------------------------------------------------ following scrape ----

def _entry_from_api(item: dict) -> dict | None:
    u, st = item.get("user") or {}, item.get("stats") or {}
    if not u.get("uniqueId"):
        return None
    return {
        "username": u.get("uniqueId"),
        "display_name": u.get("nickname") or "",
        "bio": u.get("signature") or "",
        "verified": bool(u.get("verified")),
        "private": bool(u.get("privateAccount") or u.get("secret")),
        "avatar": u.get("avatarThumb") or "",
        "followers": st.get("followerCount") or 0,
        "following": st.get("followingCount") or 0,
        "likes": st.get("heartCount") or 0,
    }


# Scroll the Following modal's list (the scrollable element holding the most
# profile links) down by `step` px and fire a scroll event so TikTok's
# infinite loader requests the next page. Incremental steps are required: a
# jump straight to scrollHeight lands on the same position twice and the
# loader's observer stops firing. Works regardless of TikTok's CSS names.
_STEP_JS = """(step) => {
    let best = null, bestLinks = -1;
    for (const el of document.querySelectorAll('*')) {
        const st = getComputedStyle(el);
        if (!/(auto|scroll)/.test(st.overflowY)) continue;
        if (el.scrollHeight <= el.clientHeight + 20) continue;
        const links = el.querySelectorAll('a[href*="/@"]').length;
        if (links > bestLinks) { bestLinks = links; best = el; }
    }
    if (!best) return false;
    best.scrollTop = best.scrollTop + step;
    best.dispatchEvent(new Event('scroll', {bubbles: true}));
    return true;
}"""


_SECUID_JS = """() => {
    try {
        const s = JSON.parse(document.querySelector(
            '#__UNIVERSAL_DATA_FOR_REHYDRATION__').textContent);
        return s.__DEFAULT_SCOPE__['webapp.user-detail'].userInfo.user.secUid;
    } catch (e) { return null; }
}"""


# In-page fetch to TikTok's own following endpoint. Because it runs inside the
# loaded tiktok.com page, TikTok's signing script (webmssdk) adds the required
# X-Bogus/signature automatically. Returns parsed JSON or null.
_FOLLOW_FETCH_JS = """async (a) => {
    const p = new URLSearchParams({
        aid:'1988', app_language:'en', app_name:'tiktok_web',
        channel:'tiktok_web', cookie_enabled:'true', count:String(a.count),
        device_platform:'web_pc', focus_state:'true', from_page:'user',
        history_len:'2', is_fullscreen:'false', is_page_visible:'true',
        os:'windows', priority_region:'', referer:'', region:'US',
        scene:String(a.scene), secUid:a.secUid, screen_height:'900',
        screen_width:'1440', tz_name:'America/New_York', webcast_language:'en',
        maxCursor:String(a.maxCursor), minCursor:'0'
    });
    try {
        const r = await fetch('/api/user/list/?' + p.toString(),
                              {credentials:'include'});
        const t = await r.text();
        return (t && t[0] === '{') ? JSON.parse(t) : null;
    } catch (e) { return null; }
}"""


def _http_paginate(page, secuid, ingest, meta, log, start_cursor="0") -> bool:
    """
    Page the entire following list via signed in-page fetches (no UI, no
    scrolling). Probes the right `scene`, then walks the cursor until hasMore
    is false. Starts from `start_cursor` so a later run can resume where the
    previous one stopped.

    TikTok rate-limits this endpoint: fire pages too fast and it returns empty
    after ~4 pages. So we PACE the requests (a couple of seconds apart) and,
    when a page comes back empty (limit hit), we BACK OFF and retry the same
    cursor rather than giving up. That is how a big list is pulled in full.
    """
    import random

    cursor = str(start_cursor or "0")
    scene = None
    # Probe for the working scene. If everything comes back empty the session
    # is rate-limited right now - wait and retry a couple of times before
    # giving up (a short throttle can clear within a run).
    for attempt in range(3):
        for sc in (21, 67, 3, 5):
            res = page.evaluate(_FOLLOW_FETCH_JS,
                                {"secUid": secuid, "scene": sc, "count": 30,
                                 "maxCursor": cursor})
            if res and res.get("userList"):
                scene = sc
                ingest(res)
                cursor = str(res.get("maxCursor") or cursor)
                log(f"signed API works (scene {sc}); paginating (paced)"
                    + (f" from cursor {start_cursor}"
                       if start_cursor not in ("0", "", None) else "") + "...")
                break
            page.wait_for_timeout(700)
        if scene is not None:
            break
        if attempt < 2:
            log("no data yet (session rate-limited); waiting 20s and retrying...")
            page.wait_for_timeout(20000)
    if scene is None:
        return False

    empty_streak = 0
    pages = 0
    while meta["has_more"] is not False and pages < 2000:
        pages += 1
        res = page.evaluate(_FOLLOW_FETCH_JS,
                            {"secUid": secuid, "scene": scene, "count": 30,
                             "maxCursor": cursor})
        if not res or not res.get("userList"):
            # rate-limited or a transient empty page: wait longer and retry
            # the SAME cursor instead of giving up.
            empty_streak += 1
            if empty_streak > 8:
                log(f"still rate-limited after retries at {meta.get('total', '?')} "
                    f"collected - stopping; press Start again later to continue")
                break
            wait_s = min(60, 8 * empty_streak)
            log(f"rate limit hit at {meta.get('total', '?')}; waiting {wait_s}s "
                f"then retrying...")
            page.wait_for_timeout(wait_s * 1000)
            continue
        empty_streak = 0
        added = ingest(res)
        cursor = str(res.get("maxCursor") or cursor)
        if added == 0 and meta["has_more"] is not True:
            break
        # pace normal pages a couple of seconds apart to stay under the limit
        page.wait_for_timeout(random.randint(1600, 2600))
    return True


def _paginate_by_cursor(page, meta, ingest, log, secuid=None) -> None:
    """
    Page through the following list using TikTok's own /api/user/list endpoint.
    Re-issues meta['template_url'] (a request that already returned data) with
    the next maxCursor from inside the page, so TikTok's signer signs each call.
    If `secuid` is given it overrides the target account. Stops when hasMore is
    false, a page comes back empty, or nothing new arrives for a few pages.
    """
    from urllib.parse import urlparse, parse_qs, urlencode

    if not meta.get("template_url"):
        return
    parsed = urlparse(meta["template_url"])
    q = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    # drop signature params (the page re-signs) and cursor (we set it)
    for k in ("X-Bogus", "_signature", "msToken", "X-Gnarly",
              "maxCursor", "minCursor"):
        q.pop(k, None)
    q["count"] = "30"
    if secuid:
        q["secUid"] = secuid

    cursor = str(meta.get("max_cursor") or "0")
    stale = 0
    for _ in range(1000):                     # 1000*30 = 30k safety ceiling
        if meta["has_more"] is False:
            break
        params = dict(q, maxCursor=cursor, minCursor="0")
        url = f"{parsed.path}?{urlencode(params)}"
        try:
            res = page.evaluate("""async (u) => {
                try {
                    const r = await fetch(u, {credentials:'include'});
                    const t = await r.text();
                    return t && t[0] === '{' ? JSON.parse(t) : null;
                } catch (e) { return null; }
            }""", url)
        except Exception:
            break
        if not res:
            break
        added = ingest(res)
        cursor = str(res.get("maxCursor") or cursor)
        if added == 0:
            stale += 1
            if stale >= 3:
                break
        else:
            stale = 0
        page.wait_for_timeout(200)


def _scrape_via_tiktokapi(secuid, cookies_list, start_cursor, ingest, log):
    """
    Pull the following list via the TikTokApi library, which signs every
    request with a FRESH msToken + X-Bogus (not the stale cookie token). That
    is what avoids the rate limit the raw approach hits after ~4 pages.

    Returns {"cursor","has_more","any"} on success, or None if TikTokApi is
    unavailable or the signed session could not be created.
    """
    import asyncio

    try:
        from TikTokApi import TikTokApi
    except Exception:
        return None

    # auth cookies for login; drop msToken so the session mints a fresh one
    cdict = {c["name"]: c["value"] for c in cookies_list
             if c.get("name") and c["name"] != "msToken"}

    async def _page_factory(context):
        # TikTok's homepage never fires "load" headless (times out). Navigate
        # with domcontentloaded so the session can be created; the signer
        # script still loads.
        page = await context.new_page()
        try:
            await page.goto("https://www.tiktok.com/",
                            wait_until="domcontentloaded", timeout=60000)
        except Exception:
            pass
        await page.wait_for_timeout(2500)
        return page

    async def run():
        result = {"cursor": str(start_cursor or "0"), "has_more": False,
                  "any": False}
        api = TikTokApi()
        try:
            await api.create_sessions(
                num_sessions=1, headless=True, cookies=[cdict],
                sleep_after=2, browser="chromium", timeout=60000,
                page_factory=_page_factory,
                suppress_resource_load_types=["image", "media", "font"])
        except Exception as e:
            log(f"TikTokApi session setup failed: {str(e)[:90]}")
            try:
                await api.close_sessions()
                await api.stop_playwright()
            except Exception:
                pass
            return None

        def _params(cursor, scene):
            return {"secUid": secuid, "count": 30, "minCursor": 0,
                    "maxCursor": cursor, "scene": scene}

        try:
            cursor = str(start_cursor or "0")
            scene = None
            for sc in (21, 67, 3, 5):          # find the working scene
                try:
                    data = await api.make_request(
                        url="https://www.tiktok.com/api/user/list/",
                        params=_params(cursor, sc), retries=2)
                except Exception:
                    data = None
                if data and data.get("userList"):
                    scene = sc
                    ingest(data)
                    cursor = str(data.get("maxCursor") or cursor)
                    result.update(any=True, has_more=bool(data.get("hasMore")),
                                  cursor=cursor)
                    log(f"TikTokApi signed OK (scene {sc}) - fresh token, "
                        f"paginating full list...")
                    break
                await asyncio.sleep(1)
            if scene is None:
                return result

            while result["has_more"]:
                try:
                    data = await api.make_request(
                        url="https://www.tiktok.com/api/user/list/",
                        params=_params(cursor, scene), retries=3)
                except Exception as e:
                    log(f"page error: {str(e)[:70]}")
                    break
                if not data or not data.get("userList"):
                    break
                ingest(data)
                cursor = str(data.get("maxCursor") or cursor)
                result.update(cursor=cursor, has_more=bool(data.get("hasMore")))
                await asyncio.sleep(0.8)
            return result
        finally:
            await api.close_sessions()
            await api.stop_playwright()

    try:
        return asyncio.run(run())
    except Exception as e:
        log(f"TikTokApi error: {str(e)[:100]}")
        return None


def scrape_following(username: str, cookies: list[dict], secuid: str = "",
                     start_cursor: str = "0", out: dict = None, ed_token: str = "",
                     progress_cb=None, log_cb=None) -> tuple[list[dict], str]:
    """
    Pull @username's full following list with NO visible window.

    Runs a headless browser only so TikTok's request-signing script is loaded,
    then calls the /api/user/list endpoint directly (signed) and pages through
    it by cursor, pacing requests to stay under TikTok's rate limit. Needs the
    account's secUid (passed in, or read from the profile page).

    progress_cb(count) is called as accounts stream in.
    Returns (list_of_accounts, error_message_or_empty).
    """
    collected: dict[str, dict] = {}
    log = log_cb or (lambda m: None)
    meta = {"has_more": None, "empty_responses": 0,
            "template_url": None, "max_cursor": None}

    def _add_entry(e: dict) -> None:
        if e and e.get("username"):
            collected[e["username"]] = e
            if progress_cb:
                progress_cb(len(collected))

    # ===== PRIMARY: EnsembleData (mobile API) - full list for ANY account =====
    if ed_token:
        target_secuid = (secuid or "").strip()
        if not target_secuid:
            prof = fetch_profile(username,
                                 {c["name"]: c["value"] for c in cookies})
            target_secuid = (prof or {}).get("secuid") or ""
        if not target_secuid:
            return [], ("need the account's secUid for the data API - paste it "
                        "in the UID field")
        log(f"using EnsembleData API (full list, any account)...")
        ed_out = {}
        ed_start_cursor = 0
        ed_start_token = ""
        if isinstance(out, dict):
            ed_start_cursor = out.get("ed_cursor_in", 0)
            ed_start_token = out.get("ed_page_token_in", "")
        ok, err = scrape_following_ed(target_secuid, ed_token, _add_entry, log,
                                      start_cursor=ed_start_cursor,
                                      start_page_token=ed_start_token, out=ed_out)
        if collected:
            if out is not None:
                out["ed_cursor"] = ed_out.get("ed_cursor", 0)
                out["ed_page_token"] = ed_out.get("ed_page_token", "")
                out["has_more"] = bool(ed_out.get("ed_more"))
                out["cursor"] = "0"
                out["secuid"] = target_secuid
            if err:
                # partial data (e.g. units ran out) - keep it but flag clearly
                log(f"PARTIAL (data API) - {len(collected)} collected; {err}")
                return list(collected.values()), f"got {len(collected)} - {err}"
            log(f"DONE (data API) - {len(collected)} following collected (complete)")
            return list(collected.values()), ""
        return [], (err or "the data API returned no accounts - check the token "
                    "and secUid")

    def _ingest(data) -> int:
        n = 0
        for item in data.get("userList") or []:
            e = _entry_from_api(item)
            if e:
                collected[e["username"]] = e
                n += 1
        meta["has_more"] = data.get("hasMore")
        if data.get("maxCursor"):
            meta["max_cursor"] = data.get("maxCursor")
        meta["total"] = len(collected)
        if progress_cb:
            progress_cb(len(collected))
        return n

    def on_response(resp):
        if "/api/user/list" not in resp.url:
            return
        try:
            body = resp.text()
            if not body.strip():
                meta["empty_responses"] += 1
                return
            data = resp.json()
            if data.get("userList"):
                # remember a request URL that actually returned people, so we
                # can paginate it directly with cursors later
                meta["template_url"] = resp.request.url
            _ingest(data)
        except Exception:
            pass

    # Resolve secUid up front (manual override, else from the profile page).
    target_secuid = (secuid or "").strip()
    if not target_secuid:
        prof = fetch_profile(username,
                             {c["name"]: c["value"] for c in cookies})
        target_secuid = (prof or {}).get("secuid") or ""

    # PRIMARY METHOD: TikTokApi with fresh-token signing (no rate-limit wall,
    # no visible window). Falls back to the browser method below if it can't
    # run or returns nothing.
    if target_secuid:
        res = _scrape_via_tiktokapi(target_secuid, cookies, start_cursor,
                                    _ingest, log)
        if res is not None and collected:
            if out is not None:
                out["cursor"] = res["cursor"] if res["has_more"] else "0"
                out["has_more"] = res["has_more"]
                out["secuid"] = target_secuid
            if res["has_more"]:
                log(f"{len(collected)} collected so far - more remain")
            else:
                log(f"DONE - {len(collected)} following collected")
            return list(collected.values()), ""
        log("TikTokApi path unavailable/empty; falling back to browser method")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return [], ("browser fallback unavailable on this server - set an "
                    "EnsembleData token in Settings to scrape the list")

    with sync_playwright() as p:
        # Headed real Chrome, parked off-screen (positive coords) so it does
        # not disturb the user. The anti-throttling flags keep the page fully
        # rendering even though the window is not visible/focused - without
        # them Chrome pauses timers & IntersectionObserver and the infinite
        # scroll never loads.
        launch_args = ["--disable-blink-features=AutomationControlled",
                       "--window-position=3000,3000",
                       "--window-size=1200,900",
                       "--disable-backgrounding-occluded-windows",
                       "--disable-renderer-backgrounding",
                       "--disable-background-timer-throttling"]
        try:
            browser = p.chromium.launch(channel="chrome", headless=True,
                                        args=launch_args)
        except Exception:
            # Chrome not installed: fall back to bundled Chromium
            browser = p.chromium.launch(headless=True, args=launch_args)
        try:
            ctx = browser.new_context(viewport={"width": 1200, "height": 900})
            if cookies:
                ctx.add_cookies(cookies)
            page = ctx.new_page()
            page.on("response", on_response)

            # Load the profile so TikTok's signing script (webmssdk) is present;
            # the page itself doesn't need to fully render for signing to work.
            page.goto(f"https://www.tiktok.com/@{username}",
                      wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3500)

            if page.locator("text=Couldn't find this account").count():
                return [], f"account @{username} not found"

            # secUid: manual override wins, else read it from the page.
            target_secuid = (secuid or "").strip() or page.evaluate(_SECUID_JS)
            if not target_secuid:
                return [], ("could not determine secUid - paste it in the "
                            "account's UID field (get it from view-source of "
                            "the profile page)")
            log(f"using secUid {target_secuid[:16]}...")

            # PRIMARY: signed in-page API pagination (no window, no scrolling).
            ok = _http_paginate(page, target_secuid, _ingest, meta, log,
                                start_cursor=start_cursor)
            if out is not None:
                out["cursor"] = str(meta.get("max_cursor") or "0")
                out["has_more"] = bool(meta.get("has_more"))
                out["secuid"] = target_secuid

            if not ok and not collected:
                if meta["empty_responses"]:
                    return [], ("TikTok returned empty/again unsigned responses "
                                "- the session is rate-limited from recent "
                                "requests; wait, then try again")
                return [], ("the signed request returned no data - the account's "
                            "following list may be private, or the signer did "
                            "not load; try again on a rested session")

            if meta["has_more"] and len(collected) >= 30:
                log(f"stopped at {len(collected)} while TikTok reported more - "
                    f"likely throttled; run Start again later to add more")
            else:
                log(f"reached the end: {len(collected)} following collected")

            ctx.close()
        finally:
            browser.close()

    if not collected:
        return [], ("no accounts loaded - make sure cookies are valid "
                    "(Settings) and the list is not private")
    return list(collected.values()), ""
