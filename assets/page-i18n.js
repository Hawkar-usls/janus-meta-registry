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
