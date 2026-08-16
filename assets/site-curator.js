(() => {
  'use strict';

  const STORAGE_KEY = 'janus-site-language-v1';
  const SCRIPT_URL = document.currentScript && document.currentScript.src;
  if (!SCRIPT_URL) return;

  const feedUrl = new URL('site-feed.json', SCRIPT_URL).href;
  const cssUrl = new URL('site-curator.css', SCRIPT_URL).href;
  const labels = {
    en: {
      kicker: 'JANUS NOW · AUTO-CURATED',
      title: 'What changed — and what is active now.',
      spotlight: 'Spotlight',
      latest: 'Latest registry updates',
      sectionLatest: 'Latest in this research surface',
      source: 'Open source object ↗',
      activity: 'activity score',
      generated: 'feed source',
      boundary: 'Auto-curation ranks activity and actionability, not truth or evidence strength.',
      empty: 'No classified recent objects for this surface yet.'
    },
    ua: {
      kicker: 'JANUS ЗАРАЗ · АВТОКУРАЦІЯ',
      title: 'Що змінилося — і що зараз активне.',
      spotlight: 'У фокусі',
      latest: 'Останні оновлення реєстру',
      sectionLatest: 'Останнє в цьому напрямі',
      source: 'Відкрити вихідний об’єкт ↗',
      activity: 'оцінка активності',
      generated: 'джерело стрічки',
      boundary: 'Автокурація ранжує активність і потребу в дії, а не істинність чи силу доказів.',
      empty: 'Для цього напряму поки немає класифікованих недавніх об’єктів.'
    },
    ru: {
      kicker: 'JANUS СЕЙЧАС · АВТОКУРАЦИЯ',
      title: 'Что изменилось — и что сейчас активно.',
      spotlight: 'В фокусе',
      latest: 'Последние обновления реестра',
      sectionLatest: 'Последнее в этом направлении',
      source: 'Открыть исходный объект ↗',
      activity: 'оценка активности',
      generated: 'источник ленты',
      boundary: 'Автокурация ранжирует активность и потребность в действии, а не истинность или силу доказательств.',
      empty: 'Для этого направления пока нет классифицированных недавних объектов.'
    }
  };

  let feedCache = null;

  function language() {
    const value = localStorage.getItem(STORAGE_KEY);
    return value === 'ua' || value === 'ru' ? value : 'en';
  }

  function surfaceFromPath() {
    const parts = location.pathname.split('/').filter(Boolean);
    const repoIndex = parts.indexOf('janus-meta-registry');
    const slug = repoIndex >= 0 ? parts[repoIndex + 1] : parts[0];
    const known = new Set(['antifuck', 'linear-a', 'wedjat', 'scoby-skingpt', 'aifc', 'fundamentum', 'gamarjoba-gen-ancvale']);
    return known.has(slug) ? slug : null;
  }

  function ensureCss() {
    if (document.querySelector('link[data-janus-curator-css]')) return;
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = cssUrl;
    link.dataset.janusCuratorCss = 'true';
    document.head.appendChild(link);
  }

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function formatDate(value, lang) {
    try {
      const locale = lang === 'ua' ? 'uk-UA' : lang === 'ru' ? 'ru-RU' : 'en-GB';
      return new Intl.DateTimeFormat(locale, { day: '2-digit', month: 'short', year: 'numeric' }).format(new Date(value));
    } catch (_) {
      return value;
    }
  }

  function itemCard(item, lang, L, spotlight = false) {
    const card = el('article', spotlight ? 'janus-now-card janus-now-card-spotlight' : 'janus-now-card');
    const top = el('div', 'janus-now-card-top');
    top.appendChild(el('span', 'janus-now-surface', item.surface || 'other'));
    top.appendChild(el('span', 'janus-now-date', formatDate(item.modified_at, lang)));
    card.appendChild(top);

    const heading = el('h3');
    const link = el('a', null, item.title);
    link.href = item.github_url;
    link.target = '_blank';
    link.rel = 'noopener';
    heading.appendChild(link);
    card.appendChild(heading);

    if (item.summary) card.appendChild(el('p', 'janus-now-summary', item.summary));
    if (item.status || item.gate) {
      const meta = el('div', 'janus-now-meta');
      if (item.status) meta.appendChild(el('span', 'janus-now-state', item.status));
      if (item.gate) meta.appendChild(el('span', 'janus-now-gate', item.gate));
      card.appendChild(meta);
    }

    const reasons = el('div', 'janus-now-reasons');
    (item.score_reasons || []).slice(0, 4).forEach(reason => reasons.appendChild(el('span', 'tag', reason)));
    card.appendChild(reasons);

    const foot = el('div', 'janus-now-foot');
    const source = el('a', 'janus-now-source', L.source);
    source.href = item.github_url;
    source.target = '_blank';
    source.rel = 'noopener';
    foot.appendChild(source);
    foot.appendChild(el('span', 'janus-now-score', `${L.activity}: ${item.score}`));
    card.appendChild(foot);
    return card;
  }

  function buildColumn(title, items, lang, L, spotlight = false) {
    const column = el('div', 'janus-now-column');
    column.appendChild(el('h2', 'janus-now-column-title', title));
    const grid = el('div', 'janus-now-grid');
    if (!items.length) grid.appendChild(el('p', 'janus-now-empty', L.empty));
    items.forEach(item => grid.appendChild(itemCard(item, lang, L, spotlight)));
    column.appendChild(grid);
    return column;
  }

  function insertionPoint() {
    const temple = document.querySelector('.temple-meaning-section');
    if (temple) return { parent: temple.parentNode, before: temple.nextSibling };
    const pagehead = document.querySelector('.pagehead');
    if (pagehead) return { parent: pagehead.parentNode, before: pagehead.nextSibling };
    const main = document.querySelector('main');
    return main ? { parent: main, before: main.firstChild } : null;
  }

  function render(feed) {
    const existing = document.querySelector('[data-janus-auto-curated]');
    if (existing) existing.remove();
    const point = insertionPoint();
    if (!point) return;

    const lang = language();
    const L = labels[lang];
    const surface = surfaceFromPath();
    const section = el('section', 'janus-now-section');
    section.dataset.janusAutoCurated = 'true';
    const wrap = el('div', 'wrap janus-now-wrap');
    wrap.appendChild(el('span', 'kicker janus-now-kicker', L.kicker));
    wrap.appendChild(el('h2', 'janus-now-title', L.title));

    const columns = el('div', 'janus-now-columns');
    if (surface) {
      const items = (feed.surfaces && feed.surfaces[surface]) || [];
      columns.appendChild(buildColumn(L.sectionLatest, items, lang, L));
      const localSpotlight = (feed.spotlight || []).filter(item => item.surface === surface);
      columns.appendChild(buildColumn(L.spotlight, localSpotlight, lang, L, true));
    } else {
      columns.appendChild(buildColumn(L.spotlight, feed.spotlight || [], lang, L, true));
      columns.appendChild(buildColumn(L.latest, feed.latest_updates || [], lang, L));
    }
    wrap.appendChild(columns);

    const boundary = el('div', 'janus-now-boundary');
    boundary.appendChild(el('span', null, L.boundary));
    const commit = (feed.source_commit || '').slice(0, 12);
    if (commit) {
      const sep = document.createTextNode(' · ');
      boundary.appendChild(sep);
      const commitLink = el('a', null, `${L.generated}: ${commit}`);
      commitLink.href = `https://github.com/Hawkar-usls/janus-meta-registry/commit/${feed.source_commit}`;
      commitLink.target = '_blank';
      commitLink.rel = 'noopener';
      boundary.appendChild(commitLink);
    }
    wrap.appendChild(boundary);
    section.appendChild(wrap);
    point.parent.insertBefore(section, point.before);
  }

  async function load() {
    ensureCss();
    try {
      const response = await fetch(feedUrl, { cache: 'no-store', headers: { Accept: 'application/json' } });
      if (!response.ok) return;
      feedCache = await response.json();
      render(feedCache);
    } catch (_) {
      // Site remains fully usable if the generated feed is temporarily unavailable.
    }
  }

  document.addEventListener('click', event => {
    const button = event.target.closest && event.target.closest('[data-lang]');
    if (!button || !feedCache) return;
    setTimeout(() => render(feedCache), 0);
  });
  window.addEventListener('storage', event => {
    if (event.key === STORAGE_KEY && feedCache) render(feedCache);
  });

  load();
})();
