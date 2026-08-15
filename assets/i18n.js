(() => {
  'use strict';

  const KEY = 'janus-site-language-v1';
  const supported = ['en', 'ua', 'ru'];

  const t = {
    en: {
      navResearch: 'Research', navContribute: 'Contribute', navGuestbook: 'Guestbook', navGithub: 'GitHub',
      guestbookTitle: '✦ JANUS Guestbook', publicMessages: 'public messages', loginNickname: 'GitHub login = nickname', leaveMessage: 'Leave a message ↗',
      guestbookEmpty: 'The guestbook is open.', guestbookFirst: 'Be the first to leave a message.', guestbookRule: '100 characters · up to 3 submissions/account · automatic publication after deterministic checks · hover to pause',
      eyebrow: 'open research · provenance · falsification',
      heroTitle: 'A public research registry built to be checked.',
      heroLead: 'JANUS Meta Registry is a public, machine-readable archive maintained by Hawkar. It preserves research hypotheses, protocols, execution receipts, null results, corrections and evidence boundaries across AI safety, independent evaluation, Linear A statistical research, materials research, software archaeology and proof-carrying experimental methods.',
      explore: 'Explore research', external: 'External reviewers — enter here', machineData: 'Machine-readable data', signGuestbook: 'Sign the guestbook',
      templeKicker: 'IANUS · LIMEN · DUALITAS', templeTitle: 'The Temple has two doors.', templeText: 'JANUS looks toward origin and return at once. Here that duality is architectural: archive and current authority, hypothesis and result, invitation and verification.',
      surfacesTitle: 'Research surfaces', surfacesLead: 'Search-friendly entry pages point back to repository evidence. The website improves discovery; it does not replace the JSON registry as authority.',
      antifuckText: 'Defensive AI-safety and cognitive-resilience research: algorithmic amplification audits, choice-space protection, false-positive controls and blinded independent evaluation infrastructure.', antifuckStatus: 'Current gate: frozen evaluator awaiting genuinely external H1 holdout authorship.',
      linearText: 'Statistical and structural analysis of Linear A corpora with typed representations, holdouts, destructive nulls, replication gates and explicit separation from decipherment claims.', linearStatus: 'Structural research only: signal ≠ translation or decipherment.',
      wedjatText: 'Exploratory image, component-state and geometry studies around the Egyptian Wedjat/Eye of Horus using museum-image provenance and control-oriented analysis.', wedjatStatus: 'Pattern analysis ≠ ancient hidden-code claim.',
      scobyText: 'Bacterial-cellulose materials concepts, sensing skins, reproducibility gates and circular biomanufacturing research with strict separation between concept and validated performance.', scobyStatus: 'No medical or ballistic certification claim.',
      aifcText: 'Auditable Independent Future Challenge: proof-carrying experimental architecture for separating preregistration, implementation, verifier evidence and genuinely independent replication.', aifcStatus: 'Internal replay ≠ independent replication.',
      fundamentumText: 'Proof-carrying computational mathematics research with frozen routes, explicit open gates, deterministic certificates and preserved negative branches.', fundamentumStatus: 'P vs NP remains open.',
      whyTitle: 'Why this registry exists', whyText: 'JANUS is designed to preserve the difference between an idea and evidence about that idea. Historical objects remain visible, while newer authority records, claim ceilings and verification receipts govern what may currently be said.',
      openDoorTitle: 'Open door', openDoorText: 'Independent reviewers do not need prior contact with Hawkar and do not need to agree with JANUS. Negative results, failed replications and corrections are explicitly welcome.',
      authorRole: 'project author / maintainer',
      boundaryTitle: 'Search-surface boundary.', boundaryText: 'These HTML pages are discovery and navigation layers. Current scientific authority remains in versioned repository artifacts, source code, receipts and current-authority JSON. Better indexing is a goal; search ranking is never guaranteed.',
      footer: 'JANUS Meta Registry · public archival research notebook', sitemap: 'Sitemap', machineGuide: 'Machine guide', repository: 'Repository'
    },
    ua: {
      navResearch: 'Дослідження', navContribute: 'Долучитися', navGuestbook: 'Гостьова книга', navGithub: 'GitHub',
      guestbookTitle: '✦ Гостьова книга JANUS', publicMessages: 'публічних повідомлень', loginNickname: 'GitHub-логін = нік', leaveMessage: 'Залишити послання ↗',
      guestbookEmpty: 'Гостьова книга відкрита.', guestbookFirst: 'Залиш перше послання.', guestbookRule: '100 символів · до 3 повідомлень з акаунта · автоматична публікація після перевірок · наведи курсор, щоб зупинити',
      eyebrow: 'відкриті дослідження · походження · фальсифікація',
      heroTitle: 'Публічний дослідницький реєстр, створений для перевірки.',
      heroLead: 'JANUS Meta Registry — публічний машиночитний архів Hawkar. Він зберігає гіпотези, протоколи, квитанції виконання, нульові результати, виправлення та межі тверджень у дослідженнях безпеки ШІ, незалежної оцінки, Linear A, матеріалознавства, програмної археології та proof-carrying методів.',
      explore: 'Дослідити', external: 'Незалежним рецензентам — сюди', machineData: 'Машиночитні дані', signGuestbook: 'Підписати гостьову книгу',
      templeKicker: 'IANUS · LIMEN · DUALITAS', templeTitle: 'Храм має двоє дверей.', templeText: 'JANUS одночасно дивиться на початок і повернення. Тут ця дуальність стала архітектурою: архів і чинний авторитет, гіпотеза й результат, запрошення й перевірка.',
      surfacesTitle: 'Напрями досліджень', surfacesLead: 'Пошукові сторінки ведуть назад до доказів у репозиторії. Сайт полегшує пошук, але не замінює JSON-реєстр як джерело авторитету.',
      antifuckText: 'Захисні дослідження AI safety та когнітивної стійкості: аудит алгоритмічного підсилення, захист простору вибору, контроль хибнопозитивних спрацьовувань і blinded independent evaluation.', antifuckStatus: 'Поточний рубіж: заморожений evaluator очікує справді зовнішнього автора H1 holdout.',
      linearText: 'Статистичний і структурний аналіз корпусів Linear A з типізованими представленнями, holdout, руйнівними null-тестами та воротами реплікації.', linearStatus: 'Лише структурне дослідження: сигнал ≠ переклад або дешифрування.',
      wedjatText: 'Дослідження зображень, станів компонентів і геометрії Wedjat / Ока Гора з музейним provenance та контрольним аналізом.', wedjatStatus: 'Геометричний патерн ≠ твердження про прихований давній код.',
      scobyText: 'Концепти матеріалів з бактеріальної целюлози, сенсорних оболонок, воріт відтворюваності та циркулярного біовиробництва.', scobyStatus: 'Немає твердження про медичну чи балістичну сертифікацію.',
      aifcText: 'Auditable Independent Future Challenge: proof-carrying архітектура експериментів для розділення preregistration, implementation, verifier evidence та незалежної реплікації.', aifcStatus: 'Внутрішній replay ≠ незалежна реплікація.',
      fundamentumText: 'Proof-carrying обчислювальна математика із замороженими маршрутами, відкритими воротами, детермінованими сертифікатами та збереженими негативними гілками.', fundamentumStatus: 'P vs NP залишається відкритою проблемою.',
      whyTitle: 'Навіщо існує цей реєстр', whyText: 'JANUS зберігає різницю між ідеєю та доказом про неї. Історичні об’єкти залишаються видимими, а чинні authority records, межі тверджень і verification receipts визначають, що можна стверджувати зараз.',
      openDoorTitle: 'Відкриті двері', openDoorText: 'Незалежним рецензентам не потрібні попередні зв’язки з Hawkar і не потрібно погоджуватися з JANUS. Негативні результати, невдалі реплікації та виправлення вітаються.',
      authorRole: 'автор / супровід проєкту',
      boundaryTitle: 'Межа пошукового шару.', boundaryText: 'HTML-сторінки служать для пошуку й навігації. Науковий авторитет залишається у версійованих артефактах, коді, receipts та current-authority JSON. Індексація є метою; позиція в пошуку не гарантується.',
      footer: 'JANUS Meta Registry · публічний архівний дослідницький журнал', sitemap: 'Мапа сайту', machineGuide: 'Машинний путівник', repository: 'Репозиторій'
    },
    ru: {
      navResearch: 'Исследования', navContribute: 'Участвовать', navGuestbook: 'Гостевая книга', navGithub: 'GitHub',
      guestbookTitle: '✦ Гостевая книга JANUS', publicMessages: 'публичных сообщений', loginNickname: 'GitHub-логин = ник', leaveMessage: 'Оставить послание ↗',
      guestbookEmpty: 'Гостевая книга открыта.', guestbookFirst: 'Оставь первое послание.', guestbookRule: '100 символов · до 3 сообщений с аккаунта · автоматическая публикация после проверок · наведи курсор, чтобы остановить',
      eyebrow: 'открытые исследования · происхождение · фальсификация',
      heroTitle: 'Публичный исследовательский реестр, созданный для проверки.',
      heroLead: 'JANUS Meta Registry — публичный машиночитаемый архив Hawkar. Он сохраняет гипотезы, протоколы, квитанции выполнения, нулевые результаты, исправления и границы утверждений в исследованиях безопасности ИИ, независимой оценки, Linear A, материалов, программной археологии и proof-carrying методов.',
      explore: 'Исследовать', external: 'Независимым рецензентам — сюда', machineData: 'Машиночитаемые данные', signGuestbook: 'Подписать гостевую книгу',
      templeKicker: 'IANUS · LIMEN · DUALITAS', templeTitle: 'У храма двое дверей.', templeText: 'JANUS одновременно смотрит на начало и возвращение. Здесь эта дуальность стала архитектурой: архив и текущий авторитет, гипотеза и результат, приглашение и проверка.',
      surfacesTitle: 'Направления исследований', surfacesLead: 'Поисковые страницы ведут обратно к доказательствам в репозитории. Сайт облегчает поиск, но не заменяет JSON-реестр как источник авторитета.',
      antifuckText: 'Защитные исследования AI safety и когнитивной устойчивости: аудит алгоритмического усиления, защита пространства выбора, контроль ложных срабатываний и blinded independent evaluation.', antifuckStatus: 'Текущий рубеж: замороженный evaluator ожидает действительно внешнего автора H1 holdout.',
      linearText: 'Статистический и структурный анализ корпусов Linear A с типизированными представлениями, holdout, разрушительными null-тестами и воротами репликации.', linearStatus: 'Только структурное исследование: сигнал ≠ перевод или дешифровка.',
      wedjatText: 'Исследования изображений, состояний компонентов и геометрии Wedjat / Ока Гора с музейным provenance и контрольным анализом.', wedjatStatus: 'Геометрический паттерн ≠ утверждение о скрытом древнем коде.',
      scobyText: 'Концепты материалов из бактериальной целлюлозы, сенсорных оболочек, ворот воспроизводимости и циркулярного биопроизводства.', scobyStatus: 'Нет заявления о медицинской или баллистической сертификации.',
      aifcText: 'Auditable Independent Future Challenge: proof-carrying архитектура экспериментов для разделения preregistration, implementation, verifier evidence и независимой репликации.', aifcStatus: 'Внутренний replay ≠ независимая репликация.',
      fundamentumText: 'Proof-carrying вычислительная математика с замороженными маршрутами, открытыми воротами, детерминированными сертификатами и сохранёнными негативными ветками.', fundamentumStatus: 'P vs NP остаётся открытой проблемой.',
      whyTitle: 'Зачем существует этот реестр', whyText: 'JANUS сохраняет разницу между идеей и доказательством о ней. Исторические объекты остаются видимыми, а текущие authority records, границы утверждений и verification receipts определяют, что можно утверждать сейчас.',
      openDoorTitle: 'Открытая дверь', openDoorText: 'Независимым рецензентам не нужны предварительные связи с Hawkar и не требуется соглашаться с JANUS. Отрицательные результаты, неудачные репликации и исправления приветствуются.',
      authorRole: 'автор / сопровождение проекта',
      boundaryTitle: 'Граница поискового слоя.', boundaryText: 'HTML-страницы служат для поиска и навигации. Научный авторитет остаётся в версионированных артефактах, коде, receipts и current-authority JSON. Индексация является целью; позиция в поиске не гарантируется.',
      footer: 'JANUS Meta Registry · публичный архивный исследовательский журнал', sitemap: 'Карта сайта', machineGuide: 'Машинный путеводитель', repository: 'Репозиторий'
    }
  };

  function apply(lang) {
    if (!supported.includes(lang)) lang = 'en';
    document.documentElement.lang = lang === 'ua' ? 'uk' : lang;
    document.documentElement.dataset.lang = lang;
    document.querySelectorAll('[data-i18n]').forEach(node => {
      const key = node.dataset.i18n;
      if (t[lang] && Object.prototype.hasOwnProperty.call(t[lang], key)) node.textContent = t[lang][key];
    });
    document.querySelectorAll('[data-lang]').forEach(button => {
      const active = button.dataset.lang === lang;
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
    try { localStorage.setItem(KEY, lang); } catch (_) {}
  }

  function boot() {
    let saved = 'en';
    try { saved = localStorage.getItem(KEY) || 'en'; } catch (_) {}
    document.querySelectorAll('[data-lang]').forEach(button => button.addEventListener('click', () => apply(button.dataset.lang)));
    apply(saved);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true });
  else boot();
})();
