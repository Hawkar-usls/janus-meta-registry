from pathlib import Path

FILES = [Path('assets/i18n.js'), Path('assets/page-i18n.js')]
MARKER = 'data-janus-holy-cringe-loader'
LOADER = r'''

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
'''

for path in FILES:
    text = path.read_text(encoding='utf-8')
    if MARKER in text or 'janusHolyCringeLoader' in text:
        continue
    path.write_text(text.rstrip() + LOADER + '\n', encoding='utf-8')
    print(f'patched {path}')
