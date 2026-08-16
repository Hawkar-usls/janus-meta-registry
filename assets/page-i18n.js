(() => {
  'use strict';

  const KEY = 'janus-site-language-v1';
  const supported = ['en', 'ua', 'ru'];
  const htmlLang = { en: 'en', ua: 'uk', ru: 'ru' };
  const suffix = { en: 'En', ua: 'Ua', ru: 'Ru' };

  function valueFor(el, lang) {
    return el.dataset[`i18n${suffix[lang]}`];
  }

  function apply(lang, persist = true) {
    if (!supported.includes(lang)) lang = 'en';

    document.documentElement.lang = htmlLang[lang];

    document.querySelectorAll('[data-i18n-en]').forEach((el) => {
      const value = valueFor(el, lang);
      if (value !== undefined) el.textContent = value;
    });

    const body = document.body;
    if (body) {
      const title = body.dataset[`title${suffix[lang]}`];
      if (title) document.title = title;
    }

    document.querySelectorAll('[data-lang]').forEach((button) => {
      const active = button.dataset.lang === lang;
      button.setAttribute('aria-pressed', String(active));
      button.classList.toggle('active', active);
    });

    if (persist) {
      try { localStorage.setItem(KEY, lang); } catch (_) {}
    }
  }

  document.addEventListener('click', (event) => {
    const button = event.target.closest('[data-lang]');
    if (!button) return;
    apply(button.dataset.lang);
  });

  let initial = 'en';
  try {
    const stored = localStorage.getItem(KEY);
    if (supported.includes(stored)) initial = stored;
  } catch (_) {}

  apply(initial, false);

  window.addEventListener('storage', (event) => {
    if (event.key === KEY && supported.includes(event.newValue)) {
      apply(event.newValue, false);
    }
  });
})();

(() => {
  'use strict';
  const loader = document.currentScript && document.currentScript.src;
  if (!loader || document.querySelector('script[data-janus-curator-loader]')) return;
  const script = document.createElement('script');
  script.src = new URL('site-curator.js', loader).href;
  script.dataset.janusCuratorLoader = 'true';
  script.async = true;
  document.head.appendChild(script);
})();

(() => {
  'use strict';
  const current = document.currentScript && document.currentScript.src;
  if (!current || document.querySelector('script[data-janus-holy-cringe-loader]')) return;
  const script = document.createElement('script');
  script.src = new URL('holy-cringe-ru.js', current).href;
  script.dataset.janusHolyCringeLoader = 'true';
  script.async = true;
  document.head.appendChild(script);
})();

