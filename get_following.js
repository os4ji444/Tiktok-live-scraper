/* ============================================================
   TikTok Following Grabber v2 — runs in YOUR browser (no limit)
   ------------------------------------------------------------
   This version lets TikTok load the list itself (properly signed)
   and quietly captures the data. It auto-opens the Following list
   and scrolls it to the end.

   HOW TO USE:
   1. Open the profile in your browser, e.g.
        https://www.tiktok.com/@yerypley778   (logged in, page loaded)
   2. F12 -> Console tab. If it blocks paste, type:  allow pasting  (Enter)
   3. Paste this whole file, press Enter.
   4. It opens the Following popup and scrolls it automatically.
      Watch the log: "collected 30... 90... 300...". Leave the tab
      focused and don't touch it.
   5. When it stops growing it downloads  following_<user>.json
   6. Dashboard -> Import list -> pick that file.
   ============================================================ */
(async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const seen = {};

  function add(list) {
    for (const it of (list || [])) {
      const u = it.user || it, s = it.stats || {};
      if (u.uniqueId && !seen[u.uniqueId]) seen[u.uniqueId] = {
        username: u.uniqueId, display_name: u.nickname || '',
        bio: u.signature || '', verified: !!u.verified,
        private: !!(u.privateAccount || u.secret),
        avatar: u.avatarThumb || '', followers: s.followerCount || 0,
        following: s.followingCount || 0, likes: s.heartCount || 0,
      };
    }
  }

  // --- Capture TikTok's own (signed) following requests -------------
  const of = window.fetch;
  window.fetch = function (...a) {
    const p = of.apply(this, a);
    try {
      const url = (typeof a[0] === 'string') ? a[0] : (a[0] && a[0].url) || '';
      if (url.includes('/api/user/list'))
        p.then(r => r.clone().json()).then(d => add(d.userList)).catch(() => {});
    } catch (e) {}
    return p;
  };
  const oOpen = XMLHttpRequest.prototype.open, oSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (m, u) { this.__u = u; return oOpen.apply(this, arguments); };
  XMLHttpRequest.prototype.send = function () {
    this.addEventListener('load', () => {
      try { if ((this.__u || '').includes('/api/user/list')) add(JSON.parse(this.responseText).userList); }
      catch (e) {}
    });
    return oSend.apply(this, arguments);
  };

  const uname = (location.pathname.match(/@([\w.]+)/) || [])[1] || 'account';

  function scroller() {
    let best = null, bl = -1;
    for (const el of document.querySelectorAll('div')) {
      const st = getComputedStyle(el);
      if (!/(auto|scroll)/.test(st.overflowY)) continue;
      if (el.scrollHeight <= el.clientHeight + 20) continue;
      const l = el.querySelectorAll('a[href*="/@"]').length;
      if (l > bl) { bl = l; best = el; }
    }
    return best;
  }
  const ready = () => scroller() || Object.keys(seen).length > 0;

  // --- Open the Following popup (only if not already open) ----------
  if (!ready()) {
    const cnt = document.querySelector('strong[data-e2e="following-count"]');
    if (cnt) cnt.click();
  }
  // wait up to ~20s for TikTok to load the first accounts
  for (let i = 0; i < 40 && !ready(); i++) await sleep(500);

  if (!ready()) {
    alert('Please click the "Following" number on the profile to open the '
      + 'list, then run this script again.');
    return;
  }

  // --- Scroll to the end, pacing so TikTok keeps loading ------------
  console.log('%c[Following Grabber] scrolling @' + uname + ' ...',
    'color:#fe2c55;font-weight:bold');
  let last = -1, stale = 0;
  while (stale < 18) {
    const el = scroller();
    if (el) {
      el.scrollTop = el.scrollTop + 700;
      el.dispatchEvent(new Event('scroll', { bubbles: true }));
      const links = el.querySelectorAll('a[href*="/@"]');
      if (links.length) links[links.length - 1].scrollIntoView({ block: 'end' });
    }
    await sleep(650);
    const n = Object.keys(seen).length;
    if (n === last) { stale++; } else { stale = 0; last = n; console.log('  collected ' + n); }
  }

  // --- Download -----------------------------------------------------
  const list = Object.values(seen);
  if (!list.length) { alert('Got 0 accounts. Open the Following list manually, then re-run.'); return; }
  const blob = new Blob([JSON.stringify({ username: uname, following: list }, null, 1)],
    { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'following_' + uname + '.json';
  a.click();
  console.log('%c[Following Grabber] DONE - ' + list.length + ' accounts saved',
    'color:#25f4ee;font-weight:bold');
  alert('Done! ' + list.length + ' accounts saved to following_' + uname
    + '.json\nDashboard -> Import list -> pick that file.');
})();
