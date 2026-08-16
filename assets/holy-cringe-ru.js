(() => {
  'use strict';

  const LANG_KEY = 'janus-site-language-v1';
  const MARK = 'janusHolyCringeDone';
  let applying = false;

  const exact = {
    navResearch: 'НИИ «ПОТРОГАТЬ ГРАФИК ПАЛКОЙ»',
    navContribute: 'ПРИНЕСТИ СВОЙ ПАКЕТ JSON',
    navGuestbook: 'СТЕНА НАДПИСЕЙ В ПОДЪЕЗДЕ',
    navGithub: 'ГИТХАБ, ТО ЕСТЬ ПОДВАЛ',
    guestbookTitle: '✦ КНИГА СВИДЕТЕЛЕЙ ТАБУРЕТКИ JANUS',
    publicMessages: 'посланий от людей, которых пока не забрал YAML',
    loginNickname: 'GitHub-логин = кличка в научном гараже',
    leaveMessage: 'Нацарапать послание на фольге ↗',
    guestbookEmpty: 'Гостевая книга открыта, сквозняк уже вошёл.',
    guestbookFirst: 'Будь первым, пока cron не проснулся.',
    guestbookRule: '100 символов · максимум 3 раза с аккаунта · потом детерминированный домовой проверит бумажки · наведи мышь, если поезд мыслей слишком бодрый',
    eyebrow: 'открытая наука · чеки · отрицательные результаты · тазик на голове',
    heroTitle: 'Публичный реестр, который зачем-то решил проверять самого себя и теперь не может остановиться.',
    explore: 'Спуститься в исследования',
    external: 'Независимым людям с отвёрткой — сюда',
    machineData: 'JSON для железных голубей',
    signGuestbook: 'Оставить след на стене',
    templeKicker: 'IANUS · LIMEN · DUALITAS · ФОЛЬГА НЕ ЗАЗЕМЛЕНА',
    templeTitle: 'У храма две двери, а техподдержки всё равно нет.',
    surfacesTitle: 'Научные подвалы',
    whyTitle: 'Зачем существует этот сарай',
    openDoorTitle: 'Дверь открыта, но петля скрипит',
    boundaryTitle: 'Граница между сайтом и серьёзным лицом.',
    footer: 'JANUS Meta Registry · архивный блокнот, который случайно получил CI',
    sitemap: 'Карта катакомб',
    machineGuide: 'Инструкция для робота-пылесоса',
    repository: 'Репозиторий-погреб'
  };

  const tails = [
    ' Короче, scientific department сегодня представлен одним табуретом, двумя null-тестами и строгим словом «receipt».',
    ' Это не доказательство, это JSON в плаще: сначала provenance, потом уже фанфары и голуби.',
    ' Янус посмотрел двумя лицами, третьего не нашёл и поэтому потребовал контрольную группу.',
    ' Где-то в углу CI нервно держит чай, потому что зелёная галочка всё ещё не равна истине.',
    ' Вымышленная Ванесса Шевченко из localStorage — именно персонаж интерфейса, не реальный человек — уже принесла пакет provenance из условного села под Сумами и просит не путать source с откровением.',
    ' Если это выглядит как вайбкод на кухонной доске — прекрасно: теперь всё равно придётся открыть исходный JSON и проверить руками.'
  ];

  const shortPrefixes = ['ну да, ', 'короче: ', 'внимание, табуретка: ', 'официально неофициально: '];

  function hash(text) {
    let h = 2166136261;
    for (const ch of String(text)) {
      h ^= ch.charCodeAt(0);
      h = Math.imul(h, 16777619);
    }
    return h >>> 0;
  }

  function keyFor(el) {
    return el.dataset.i18n || el.dataset.i18nKey || el.getAttribute('data-i18n') || '';
  }

  function protectedNode(el) {
    return !!el.closest('code, pre, samp, kbd, script, style, [data-holy-cringe-preserve], .code, .source-path');
  }

  function rewrite(text, key = '') {
    const clean = String(text || '').replace(/\s+/g, ' ').trim();
    if (!clean) return clean;
    if (exact[key]) return exact[key];
    if (/^(https?:|[A-Fa-f0-9]{32,}|\$\.|[A-Z0-9_.-]+\.json$)/.test(clean)) return clean;
    const h = hash(key + '|' + clean);
    if (clean.length < 34) return shortPrefixes[h % shortPrefixes.length] + clean;
    return clean + tails[h % tails.length];
  }

  function candidates(root = document) {
    return root.querySelectorAll([
      '[data-i18n]',
      '[data-i18n-en]',
      '.janus-now-kicker',
      '.janus-now-title',
      '.janus-now-column-title',
      '.janus-now-source',
      '.janus-now-boundary',
      '.janus-now-empty'
    ].join(','));
  }

  function ensureBadge() {
    let badge = document.querySelector('[data-holy-cringe-ru-badge]');
    if (!badge) {
      badge = document.createElement('div');
      badge.dataset.holyCringeRuBadge = 'true';
      badge.textContent = '△ ru · СВЯТОЙ КРИНЖ · ПАРОДИЙНЫЙ СЛОЙ';
      badge.title = 'Абсурдистский presentation-layer. Исходные JSON и научные записи не изменяются.';
      Object.assign(badge.style, {
        position: 'fixed', left: '10px', bottom: '10px', zIndex: '9999',
        padding: '6px 9px', border: '1px solid rgba(210,220,230,.45)',
        background: 'linear-gradient(135deg,rgba(160,170,180,.18),rgba(8,12,18,.92),rgba(220,225,230,.12))',
        color: '#cfd8df', font: '700 10px/1.2 monospace', letterSpacing: '.06em',
        borderRadius: '999px', boxShadow: '0 0 18px rgba(190,210,220,.12)', pointerEvents: 'none'
      });
      document.body.appendChild(badge);
    }
  }

  function removeBadge() {
    document.querySelector('[data-holy-cringe-ru-badge]')?.remove();
  }

  function transformRoot(root = document) {
    if (applying) return;
    let lang = 'en';
    try { lang = localStorage.getItem(LANG_KEY) || 'en'; } catch (_) {}
    if (lang !== 'ru') {
      document.body?.removeAttribute('data-holy-cringe-ru');
      removeBadge();
      document.querySelectorAll(`[data-${MARK.replace(/[A-Z]/g, m => '-' + m.toLowerCase())}]`).forEach(el => {
        delete el.dataset[MARK];
      });
      return;
    }

    applying = true;
    try {
      document.body?.setAttribute('data-holy-cringe-ru', 'true');
      ensureBadge();
      candidates(root).forEach(el => {
        if (protectedNode(el) || el.dataset[MARK] === 'true') return;
        const current = el.textContent;
        if (!current || !current.trim()) return;
        el.textContent = rewrite(current, keyFor(el));
        el.dataset[MARK] = 'true';
      });
    } finally {
      applying = false;
    }
  }

  window.JANUSHolyCringeRU = Object.freeze({ rewrite, transformRoot });

  document.addEventListener('click', event => {
    if (!event.target.closest?.('[data-lang]')) return;
    setTimeout(() => {
      document.querySelectorAll('[data-janus-holy-cringe-done]').forEach(el => delete el.dataset[MARK]);
      transformRoot();
    }, 25);
  });

  window.addEventListener('storage', event => {
    if (event.key === LANG_KEY) setTimeout(() => transformRoot(), 0);
  });

  const observer = new MutationObserver(records => {
    if (applying) return;
    let ru = false;
    try { ru = localStorage.getItem(LANG_KEY) === 'ru'; } catch (_) {}
    if (!ru) return;
    for (const record of records) {
      for (const node of record.addedNodes) {
        if (node.nodeType === 1) transformRoot(node.matches?.('[data-i18n],[data-i18n-en]') ? node.parentElement || document : node);
      }
    }
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      transformRoot();
      observer.observe(document.body, { childList: true, subtree: true });
    }, { once: true });
  } else {
    transformRoot();
    observer.observe(document.body, { childList: true, subtree: true });
  }
})();
