(() => {
  'use strict';

  const REPO = 'Hawkar-usls/janus-meta-registry';
  const API = `https://api.github.com/repos/${REPO}/issues?state=open&per_page=100&sort=created&direction=asc`;
  const CACHE_URL = './guestbook/messages.json';
  const QUARANTINE_URL = './guestbook/quarantine.json';
  const ISSUE_FORM_URL = `https://github.com/${REPO}/issues/new?template=guestbook.yml`;
  const MAX_PER_LOGIN = 3;
  const MAX_CHARS = 100;
  const LIVE_CACHE_KEY = 'janus-guestbook-live-v1';
  const LIVE_CACHE_MS = 60 * 1000;

  const latinMap = {
    '@': 'a', '$': 's', '0': 'o', '1': 'i', '3': 'e', '4': 'a', '5': 's', '7': 't',
    'а': 'a', 'е': 'e', 'о': 'o', 'р': 'p', 'с': 'c', 'х': 'x', 'у': 'y', 'к': 'k', 'м': 'm', 'т': 't', 'в': 'b'
  };

  const prohibited = [
    /f+u+c+k+/i, /s+h+i+t+/i, /b+i+t+c+h+/i, /c+u+n+t+/i,
    /a+s+s+h+o+l+e+/i, /i+d+i+o+t+/i, /m+o+r+o+n+/i,
    /s+t+u+p+i+d+/i, /d+u+m+b+a+s+s+/i,
    /б+л+[яа]+[дт]+/i, /с+у+к+[аои]+/i, /х+[уy]+[йияе]+/i,
    /п+и+з+д+/i, /[е]+б+(?:а|у|л|н|т|е|и|ы)/i, /й+о+б+/i,
    /м+у+д+[ао]+к+/i, /м+р+[ао]+з+/i, /д+е+б+и+л+/i,
    /и+д+и+о+т+/i, /у+р+о+д+/i, /т+в+[ао]+р+/i,
    /у+б+л+[юу]+д+/i, /г+о+в+н+/i, /д+е+р+[ьъ]*м+/i,
    /т+у+п+(?:о+й+|а+я+|о+е+|и+ц+а+)/i, /н+и+ч+т+о+ж+/i,
    /д+о+в+б+о+й+о+б+/i
  ];

  function nfkcLower(text) {
    return String(text || '').normalize('NFKC').toLowerCase().replaceAll('ё', 'е');
  }

  function compactCyr(text) {
    return Array.from(nfkcLower(text)).filter(ch => /[\p{L}\p{N}]/u.test(ch)).join('');
  }

  function compactLatin(text) {
    return Array.from(nfkcLower(text))
      .map(ch => latinMap[ch] || ch)
      .filter(ch => /[\p{L}\p{N}]/u.test(ch))
      .join('');
  }

  function mentionsJanus(text) {
    const cyr = compactCyr(text);
    const lat = compactLatin(text);
    if (cyr.includes('янус')) return true;
    if (lat.includes('janus') || lat.includes('ianus') || lat.includes('yanus')) return true;
    const translitMap = { 'я': 'ya', 'н': 'n', 'у': 'u', 'с': 's', 'а': 'a' };
    const translit = Array.from(nfkcLower(text))
      .map(ch => translitMap[ch] || ch)
      .filter(ch => /[\p{L}\p{N}]/u.test(ch))
      .join('');
    return translit.includes('yanus');
  }

  function hasProhibited(text) {
    const readable = nfkcLower(text);
    const cyr = compactCyr(text);
    const lat = compactLatin(text);
    return prohibited.some(rx => rx.test(readable) || rx.test(cyr) || rx.test(lat));
  }

  function acceptedByRespectRule(message) {
    return !(mentionsJanus(message) && hasProhibited(message));
  }

  function parseIssueForm(body) {
    const text = String(body || '');
    const heading = /^###\s+(.+?)\s*$/gm;
    const matches = [...text.matchAll(heading)];
    const fields = {};
    matches.forEach((m, index) => {
      const start = m.index + m[0].length;
      const end = index + 1 < matches.length ? matches[index + 1].index : text.length;
      fields[m[1].trim().toLowerCase()] = text.slice(start, end).trim();
    });
    return fields;
  }

  function oneLine(text) {
    return String(text || '')
      .replace(/<!--.*?-->/gs, '')
      .replace(/\0/g, '')
      .replace(/\s+/g, ' ')
      .trim();
  }

  function issueSubmission(issue) {
    if (!issue || issue.pull_request) return null;
    if (!String(issue.title || '').startsWith('[GUESTBOOK]')) return null;
    const login = issue.user && issue.user.login ? String(issue.user.login) : '';
    if (!login) return null;
    const fields = parseIssueForm(issue.body || '');
    return {
      issue_number: Number(issue.number),
      issue_url: String(issue.html_url || ''),
      author_login: login,
      display_name: `@${login}`,
      message: oneLine(fields.message || ''),
      public_consent: /\[[xX]\]/.test(String(fields['public display'] || '')),
      created_at: String(issue.created_at || ''),
      render_in_ticker: true
    };
  }

  function liveSubmissionAccepted(entry) {
    return Boolean(
      entry &&
      entry.public_consent &&
      entry.message &&
      entry.message.length <= MAX_CHARS &&
      acceptedByRespectRule(entry.message)
    );
  }

  async function fetchJson(url) {
    const response = await fetch(url, { cache: 'no-store' });
    if (!response.ok) throw new Error(`${url}: ${response.status}`);
    return response.json();
  }

  async function fetchLiveIssues() {
    try {
      const cached = JSON.parse(localStorage.getItem(LIVE_CACHE_KEY) || 'null');
      if (cached && Date.now() - cached.savedAt < LIVE_CACHE_MS && Array.isArray(cached.issues)) {
        return cached.issues;
      }
    } catch (_) {}

    const response = await fetch(API, { headers: { 'Accept': 'application/vnd.github+json' } });
    if (!response.ok) throw new Error(`GitHub API: ${response.status}`);
    const issues = await response.json();
    try {
      localStorage.setItem(LIVE_CACHE_KEY, JSON.stringify({ savedAt: Date.now(), issues }));
    } catch (_) {}
    return issues;
  }

  function mergeEntries(cache, quarantine, issues) {
    const accepted = Array.isArray(cache.entries) ? [...cache.entries] : [];
    const quarantined = Array.isArray(quarantine.entries) ? quarantine.entries : [];
    const processed = new Set([
      ...accepted.map(x => Number(x.issue_number)),
      ...quarantined.map(x => Number(x.issue_number))
    ]);

    const counts = new Map();
    const addCount = login => {
      const key = String(login || '').toLowerCase();
      if (!key) return;
      counts.set(key, (counts.get(key) || 0) + 1);
    };
    accepted.forEach(x => addCount(x.author_login));
    quarantined.forEach(x => addCount(x.author_login));

    let liveQuarantineCount = 0;
    const live = (Array.isArray(issues) ? issues : [])
      .map(issueSubmission)
      .filter(Boolean)
      .sort((a, b) => new Date(a.created_at) - new Date(b.created_at));

    for (const entry of live) {
      if (processed.has(entry.issue_number)) continue;
      const key = entry.author_login.toLowerCase();
      const count = counts.get(key) || 0;
      processed.add(entry.issue_number);

      if (count >= MAX_PER_LOGIN) {
        counts.set(key, count + 1);
        liveQuarantineCount += 1;
        continue;
      }

      counts.set(key, count + 1);
      if (!liveSubmissionAccepted(entry)) {
        liveQuarantineCount += 1;
        continue;
      }
      accepted.push(entry);
    }

    const dedup = new Map();
    accepted
      .filter(x => x && x.render_in_ticker !== false && x.message && x.author_login)
      .forEach(entry => dedup.set(Number(entry.issue_number), entry));

    return {
      entries: [...dedup.values()].sort((a, b) => new Date(a.created_at) - new Date(b.created_at)),
      quarantineCount: quarantined.length + liveQuarantineCount
    };
  }

  function createRun(entries, quarantineCount) {
    const run = document.createElement('div');
    run.className = 'guestbook-run';

    const display = [...entries];
    if (quarantineCount > 0) {
      const insertAt = Math.min(3, display.length);
      display.splice(insertAt, 0, {
        system_warning: true,
        message: `House rule withheld ${quarantineCount} submission${quarantineCount === 1 ? '' : 's'} from the public ticker.`
      });
    }

    display.forEach((entry, index) => {
      if (index) {
        const sep = document.createElement('span');
        sep.className = 'guestbook-separator';
        sep.textContent = '✦';
        run.appendChild(sep);
      }

      if (entry.system_warning) {
        const warning = document.createElement('span');
        warning.className = 'guestbook-system-warning';
        warning.textContent = entry.message;
        run.appendChild(warning);
        return;
      }

      const item = document.createElement('a');
      item.className = 'guestbook-message';
      item.href = entry.issue_url || ISSUE_FORM_URL;
      item.target = '_blank';
      item.rel = 'noopener noreferrer';

      const who = document.createElement('strong');
      who.textContent = `${entry.display_name || '@' + entry.author_login}: `;
      const msg = document.createElement('span');
      msg.textContent = entry.message;
      item.append(who, msg);
      run.appendChild(item);
    });
    return run;
  }

  function render(entries, quarantineCount = 0) {
    const host = document.getElementById('janus-guestbook');
    if (!host) return;
    const track = host.querySelector('.guestbook-track');
    const empty = host.querySelector('.guestbook-empty');
    const count = host.querySelector('[data-guestbook-count]');
    if (count) count.textContent = String(entries.length);

    if (!entries.length && quarantineCount === 0) {
      if (empty) empty.hidden = false;
      if (track) track.hidden = true;
      return;
    }

    if (empty) empty.hidden = true;
    track.hidden = false;
    track.replaceChildren(
      createRun(entries, quarantineCount),
      createRun(entries, quarantineCount)
    );
    const visibleItems = entries.length + (quarantineCount > 0 ? 1 : 0);
    const seconds = Math.max(14, visibleItems * 5);
    track.style.setProperty('--ticker-duration', `${seconds}s`);
  }

  async function boot() {
    const host = document.getElementById('janus-guestbook');
    if (!host) return;
    const formLinks = host.querySelectorAll('[data-guestbook-form]');
    formLinks.forEach(link => { link.href = ISSUE_FORM_URL; });

    let cache = { entries: [] };
    let quarantine = { entries: [] };
    try { cache = await fetchJson(CACHE_URL); } catch (_) {}
    try { quarantine = await fetchJson(QUARANTINE_URL); } catch (_) {}

    try {
      const issues = await fetchLiveIssues();
      const merged = mergeEntries(cache, quarantine, issues);
      render(merged.entries, merged.quarantineCount);
      host.dataset.live = 'true';
    } catch (_) {
      render(Array.isArray(cache.entries) ? cache.entries : [], Array.isArray(quarantine.entries) ? quarantine.entries.length : 0);
      host.dataset.live = 'false';
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot, { once: true });
  } else {
    boot();
  }
})();
