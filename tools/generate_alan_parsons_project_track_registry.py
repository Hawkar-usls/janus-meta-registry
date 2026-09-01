#!/usr/bin/env python3
import json, re, unicodedata
from pathlib import Path

ROOT = Path('data/music/the-alan-parsons-project')

ALBUMS = [
  {
    'album':'Tales of Mystery and Imagination','year':1976,'slug':'1976-tales-of-mystery-and-imagination',
    'official_url':'https://www.the-alan-parsons-project.com/tales-of-mystery-and-imagination',
    'official_context':'Based on the life and work of Edgar Allan Poe; the album turns Poe material into a connected musical-literary cycle.',
    'user_context':'Дебют по мотивам мистических рассказов Эдгара По.',
    'tracks':[
      ('A Dream Within a Dream',True,'Ненадёжность восприятия и памяти','Сон + Сон = Реальность под вопросом','REALITY_REQUIRES_WITNESS'),
      ('The Raven',False,'Горе, которое превращается в навязчивое присутствие','Утрата + Повторение + Память = Невозможность отпустить','GRIEF_RETURNS_AS_SIGNAL'),
      ('The Tell-Tale Heart',False,'Скрытая вина, которая сама раскрывает преступление','Скрытие + Вина + Внутренний шум = Саморазоблачение','GUILT_BREAKS_SECRECY'),
      ('The Cask of Amontillado',False,'Месть как замкнутая архитектура ловушки','Обида + План + Замыкание = Необратимая расплата','REVENGE_BUILDS_A_TOMB'),
      ('(The System of) Doctor Tarr and Professor Fether',False,'Инверсия авторитета: система теряет способность отличать норму от безумия','Институт + Переворот ролей = Авторитет без истины','AUTHORITY_NEEDS_EXTERNAL_CHECK'),
      ('The Fall of the House of Usher: Prelude',True,'Порог перед распадом системы','Предчувствие + Структурная трещина = Неизбежный вход в кризис','DECAY_HAS_A_PRELUDE'),
      ('The Fall of the House of Usher: Arrival',True,'Вход наблюдателя в уже нестабильный мир','Прибытие + Нестабильная система = Свидетель внутри кризиса','ENTER_THE_FAILING_SYSTEM'),
      ('The Fall of the House of Usher: Intermezzo',True,'Подвешенное состояние между причиной и обвалом','Пауза + Напряжение = Неразрешённый переход','SUSPEND_BEFORE_VERDICT'),
      ('The Fall of the House of Usher: Pavane',True,'Красота и ритуал, сохраняющиеся внутри распада','Форма + Красота + Декаданс = Достоинство перед крахом','FORM_SURVIVES_DECAY'),
      ('The Fall of the House of Usher: Fall',True,'Коллапс после накопленной структурной нестабильности','Трещины + Нагрузка -> Коллапс','UNRESOLVED_DECAY_COLLAPSES'),
      ('To One in Paradise',False,'Идеализированная память о потерянном рае','Любовь + Утрата + Память = Рай как внутренний архив','PARADISE_SURVIVES_AS_MEMORY')]
  },
  {
    'album':'I Robot','year':1977,'slug':'1977-i-robot','official_url':'https://www.the-alan-parsons-project.com/i-robot',
    'official_context':'Originally linked to Asimov, then broadened into a theme of humans versus artificial intelligence.',
    'user_context':'Вдохновлен научно-фантастическими трудами Айзека Азимова.',
    'tracks':[
      ('I Robot',True,'Появление машинного субъекта как зеркала человека','Машина + Самоопределение = Новый наблюдатель','MACHINE_IDENTITY_ENTERS'),
      ('I Wouldn’t Want To Be Like You',False,'Отказ от копирования чужой модели личности','Чужая модель + Сопротивление = Сохранение идентичности','IMITATION_IS_NOT_IDENTITY'),
      ('Some Other Time',False,'Смещение во времени и ощущение несвоевременности','Я + Не-своё-время = Временное отчуждение','TIME_BINDING_MATTERS'),
      ('Breakdown',False,'Точка, где система больше не скрывает внутренний отказ','Нагрузка > Устойчивость => Breakdown','FAILURE_REVEALS_STRUCTURE'),
      ('Don’t Let it Show',False,'Маска устойчивости поверх уязвимости','Уязвимость + Маскирование = Ложная стабильность','SURFACE_CALM_NEQ_INTERNAL_STATE'),
      ('The Voice',False,'Команда или внутренний голос как источник управления','Голос + Доверие = Управление; источник должен быть проверен','VOICE_NEEDS_SOURCE_CHECK'),
      ('Nucleus',True,'Минимальное ядро, из которого разворачивается система','Ядро + Правила = Развёртывание','PROTECT_THE_CORE'),
      ('Day After Day (The Show Must Go On)',False,'Продолжение работы после истощения как цикл исполнения','Повтор + Обязанность = Продолжение процесса','PERSISTENCE_CAN_BECOME_LOOP'),
      ('Total Eclipse',False,'Полное затмение сигнала, смысла или управления','Свет - доступ = Eclipse','LOSS_OF_SIGNAL_IS_NOT_LOSS_OF_WORLD'),
      ('Genesis Ch.1 V.32',True,'Воображаемый следующий стих после завершённого акта создания','Creation_31 + Human_Extension = Verse_32','THE_NEXT_VERSE_IS_BUILT')]
  },
  {
    'album':'Pyramid','year':1978,'slug':'1978-pyramid','official_url':'https://www.the-alan-parsons-project.com/pyramid',
    'official_context':'Built around the late-1970s fascination with pyramids and alleged pyramid power, including a satirical edge.',
    'user_context':'Посвящен мистике Древнего Египта.',
    'tracks':[
      ('Voyager',True,'Путешествие к неизвестному как начало проверки мифа','Дистанция + Любопытство = Вход в неизвестное','GO_TO_THE_UNKNOWN'),
      ('What Goes Up',False,'Подъём содержит в себе вопрос о неизбежном падении','Rise -> Peak -> Return','ASCENT_NEEDS_RETURN_MODEL'),
      ('The Eagle Will Rise Again',False,'Возрождение после падения','Падение + Память + Воля = Новый подъём','RISE_AGAIN_WITH_MEMORY'),
      ('One More River',False,'Ещё один порог между текущим состоянием и новым','Берег_A + Переход + Берег_B = Изменённое состояние','CROSS_THE_NEXT_THRESHOLD'),
      ('Can’t Take it With You',False,'Материальное не переживает конечный переход','Накопление - Переносимость = Пустая собственность','POSSESSION_IS_NOT_PORTABLE'),
      ('In the Lap of the Gods',True,'Граница человеческого контроля и неизвестного','Контроль < Неопределённость => Смирение','UNKNOWN_MUST_REMAIN_UNKNOWN'),
      ('Pyramania',False,'Сатира на превращение символа в псевдонаучную уверенность','Символ + Желание верить - Проверка = Мания','SIGN_NEQ_SOURCE'),
      ('Hyper-Gamma-Spaces',True,'Спекулятивный выход за пределы обычного масштаба','Норма + Экстраполяция = Пространство гипотез','SPECULATION_NEEDS_BOUNDARIES'),
      ('Shadow of a Lonely Man',False,'Одиночество после исчезновения больших обещаний','Миф распался + Человек остался = Тень','AFTER_THE_MYTH_THE_WITNESS_REMAINS')]
  },
  {
    'album':'Eve','year':1979,'slug':'1979-eve','official_url':'https://www.the-alan-parsons-project.com/eve',
    'official_context':'Evolved from an idea about great women into a broader look at women’s strengths and the problems they face in a world of men.',
    'user_context':'Концептуальный взгляд на женщину и её отношения с мужчинами.',
    'tracks':[
      ('Lucifer',True,'Искушение как притягательная неоднозначность','Свет + Тень + Выбор = Испытание','TEMPTATION_IS_A_GATE'),
      ('You Lie Down With Dogs',False,'Близость к разрушительной среде имеет последствия','Среда + Близость -> Наследование риска','PROXIMITY_HAS_COST'),
      ('I’d Rather Be A Man',False,'Защитная роль и гендерная позиция как маска конфликта','Роль + Страх + Самооправдание = Жёсткая идентичность','ROLE_IS_NOT_WHOLE_SELF'),
      ('You Won’t Be There',False,'Отсутствие другого человека как структурная пустота','Ожидание - Присутствие = Разрыв','ABSENCE_IS_DATA'),
      ('Winding Me Up',False,'Манипуляция, которая превращает отношения в натянутый механизм','Давление + Повтор = Эмоциональная пружина','MANIPULATION_STORES_TENSION'),
      ('Damned If I Do',False,'Двойная ловушка, где оба выбора имеют цену','Choice_A = Cost; Choice_B = Cost','DOUBLE_BIND_REQUIRES_NEW_FRAME'),
      ('Don’t Hold Back',False,'Возврат субъектности через действие','Страх - Удерживание + Действие = Агентность','AGENCY_REQUIRES_RELEASE'),
      ('Secret Garden',False,'Внутреннее пространство, которое нельзя полностью отдавать внешнему миру','Граница + Тайна + Уход = Сохранённое Я','PROTECT_INNER_SPACE'),
      ('If I Could Change Your Mind',False,'Желание изменить другого сталкивается с автономией другого','Убеждение + Любовь - Контроль = Уважение границы','LOVE_NEQ_CONTROL')]
  },
  {
    'album':'The Turn of a Friendly Card','year':1980,'slug':'1980-the-turn-of-a-friendly-card','official_url':'https://www.the-alan-parsons-project.com/the-turn-of-a-friendly-card',
    'official_context':'Inspired by casino theatricality; gambling risk is used as a parallel for risks in life.',
    'user_context':'Альбом об азартных играх и человеческих пороках.',
    'tracks':[
      ('May Be a Price to Pay',False,'Любое решение может иметь скрытую цену','Выбор + Последствие = Цена','EVERY_BET_HAS_COST'),
      ('Games People Play',False,'Социальные отношения как стратегическая игра','Люди + Правила + Скрытые цели = Игра','MODEL_THE_GAME_NOT_THE_MASK'),
      ('Time',False,'Необратимость времени как главный лимит любой ставки','t -> t+1; возврат байтов невозможен без памяти','TIME_IS_THE_NONREFUNDABLE_STAKE'),
      ('I Don’t Wanna Go Home',False,'Отказ завершить игру, когда выход эмоционально проигрышен','Игра + Привязанность > Сигнал выхода','KNOW_WHEN_EXIT_FAILS'),
      ('The Gold Bug',True,'Блеск ценности как приманка для поиска и одержимости','Ценность? + Поиск = Погоня','VALUE_MUST_BE_VERIFIED'),
      ('The Turn of a Friendly Card (Part 1)',False,'Случайный поворот меняет траекторию игрока','Состояние + Случайный поворот = Новая ветка','CHANCE_REWRITES_PATH'),
      ('The Turn of a Friendly Card: Snake Eyes',False,'Редкий исход превращает уверенность в проигрыш','Ставка + Неблагоприятный бросок = Потеря','LOW_PROBABILITY_IS_NOT_ZERO'),
      ('The Turn of a Friendly Card: The Ace of Swords',True,'Решение, которое разрезает неопределённость','Неопределённость + Решение = Разделение ветвей','CUT_THE_BRANCH_CLEANLY'),
      ('The Turn of a Friendly Card: Nothing Left to Lose',False,'После исчерпания ставок меняется сама функция риска','Активы -> 0 => Страх потери меняет смысл','ZERO_STAKE_CHANGES_POLICY'),
      ('The Turn of a Friendly Card (Part 2)',False,'Возврат к исходной теме после прохождения цены риска','Игра + Потери + Память = Второй взгляд','RETURN_WITH_LEDGER')]
  },
  {
    'album':'Eye in the Sky','year':1982,'slug':'1982-eye-in-the-sky','official_url':'https://www.the-alan-parsons-project.com/eye-in-the-sky',
    'official_context':'About belief systems—religious, political, luck/gambling—and the recurring idea of someone looking down; also surveillance and military meanings.',
    'user_context':'Самый коммерчески успешный и узнаваемый альбом группы.',
    'tracks':[
      ('Sirius',True,'Входной маяк: сигнал появляется до слов и поднимает наблюдателя к теме взгляда сверху','BEACON -> ATTENTION -> OBSERVATION','BEACON_BEFORE_VERDICT'),
      ('Eye In The Sky',False,'Наблюдение, власть и убеждение в способности читать другого','Observer + Authority - Verification = Surveillance power','THE_EYE_MUST_NOT_BECOME_THE_VERDICT'),
      ('Children of the Moon',False,'Поколение внутри чужих систем убеждений, которое поздно замечает последствия','Inherited belief + Blind leadership = Lost generation','BELIEF_NEEDS_INDEPENDENT_CHECK'),
      ('Gemini',False,'Двойственность и связь двух сходных, но не тождественных субъектов','Witness_A + Witness_B = Pair; A != B','TWO_WITNESSES_ONE_RELATION'),
      ('Silence and I',False,'Молчание как внутренний собеседник и контейнер невыраженного','Silence + Self = Hidden witness','SILENCE_IS_NOT_NEGATIVE_EVIDENCE'),
      ('You’re Gonna Get Your Fingers Burned',False,'Иллюзия и риск наказывают чрезмерную уверенность','Illusion + Overconfidence -> Burn','DECEPTION_PUNISHES_CERTAINTY'),
      ('Psychobabble',False,'Интерпретационный шум может выглядеть как объяснение, не являясь им','Words - Discrimination = Noise','EXPLANATION_NEEDS_TEST'),
      ('Mammagamma',True,'Машиноподобный пульс процесса без обязательного нарратива','Pattern + Repetition = Process signature','PATTERN_NEQ_MESSAGE'),
      ('Step By Step',False,'Надёжное продвижение через малые проверяемые переходы','Delta_1 + Delta_2 + ... = Advance','STATE_MUST_ADVANCE_STEPWISE'),
      ('Old and Wise',False,'Поздняя перспектива превращает память и смертность в критерий важного','Time + Loss + Memory = Wisdom','MEMORY_OUTLIVES_NOISE')]
  },
  {
    'album':'Ammonia Avenue','year':1984,'slug':'1984-ammonia-avenue','official_url':'https://www.the-alan-parsons-project.com/ammonia-avenue',
    'official_context':'Explores mutual misunderstanding between industrial/scientific development and the public, inspired by an immense chemical-plant avenue of pipes.',
    'user_context':'О влиянии промышленного и научного прогресса на общество.',
    'tracks':[
      ('Prime Time',False,'Момент максимальной публичной видимости, когда образ может заменить содержание','Visibility + Attention != Truth','PUBLICITY_NEQ_VALIDATION'),
      ('Let Me Go Home',False,'Отчуждение от системы и желание вернуться к человеческому масштабу','System scale - Belonging = Homesickness','HUMAN_SCALE_MATTERS'),
      ('One Good Reason',False,'Требование достаточного основания перед согласием','Claim -> Need(reason)','NO_PROMOTION_WITHOUT_REASON'),
      ('Since the Last Goodbye',False,'Изменения измеряются относительно последней точки разрыва','State_now - State_goodbye = Delta','COMPARE_TO_LAST_WITNESS'),
      ('Don’t Answer Me',False,'Закрытие канала как защита от повторяющегося конфликта','Channel open + Harm -> Close channel','NO_ANSWER_CAN_BE_A_BOUNDARY'),
      ('Dancing on a High Wire',False,'Баланс между прогрессом и риском на узкой грани','Benefit - Risk margin -> Stability','MEASURE_THE_MARGIN'),
      ('You Don’t Believe',False,'Разрыв доверия между знанием и восприятием','Evidence + Failed trust = Communication gap','TRUTH_NEEDS_TRANSLATION'),
      ('Pipeline',True,'Невидимая инфраструктура, по которой реально течёт система','Nodes + Flow + Pipe = Hidden dependency','TRACE_THE_PIPELINE'),
      ('Ammonia Avenue',False,'Индустриальный мир без человека как образ разрыва науки и общества','Science + Industry - Human translation = Alienation','BUILD_THE_BRIDGE_BETWEEN_LAB_AND_WORLD')]
  },
  {
    'album':'Vulture Culture','year':1985,'slug':'1985-vulture-culture','official_url':'https://www.the-alan-parsons-project.com/vulture-culture',
    'official_context':'A critique of increasing ruthlessness under stark economic pressures and exploitation of people in difficulty.',
    'user_context':'Острая критика потребительского общества («культуры стервятников»).',
    'tracks':[
      ('Let’s Talk About Me',False,'Самоцентричность превращает диалог в монолог выгоды','Dialogue - Other = Self-market','SELF_INTEREST_CAN_EAT_DIALOGUE'),
      ('Separate Lives',False,'Социальная близость может скрывать фактическую разобщённость','Shared space - Shared life = Separation','PROXIMITY_NEQ_CONNECTION'),
      ('Days Are Numbers (The Traveller)',False,'Дни становятся конечным счётчиком движения','Life = finite(day_1...day_n)','COUNT_DAYS_BUT_PRESERVE_MEANING'),
      ('Sooner Or Later',False,'Отложенные последствия всё равно входят в систему','Deferred consequence -> Eventually due','DEBT_RETURNS'),
      ('Vulture Culture',False,'Экономическая система может вознаграждать выгоду из чужой слабости','Distress + Predation = Extraction','DO_NOT_FEED_ON_WEAKNESS'),
      ('Hawkeye',True,'Высокая точка наблюдения: видеть далеко, но не путать обзор с моральным правом','Wide view + No empathy = Predatory eye','OBSERVATION_NEEDS_ETHICS'),
      ('Somebody Out There',False,'Поиск другого как сопротивление социальной пустоте','Isolation + Search = Possible connection','KEEP_CALLING_FOR_THE_OTHER'),
      ('The Same Old Sun',False,'Общий мир остаётся одним, несмотря на социальные разрывы','Different lives + Same sun = Shared world','ONE_WORLD_MANY_LIVES')]
  },
  {
    'album':'Stereotomy','year':1986,'slug':'1986-stereotomy','official_url':'https://www.the-alan-parsons-project.com/stereotomy',
    'official_context':'The title comes from a scientific cutting term used by Poe; the album reflects pressures of the modern world.',
    'user_context':'Пользователь указал 1985 и связал альбом с давлением славы и шоу-бизнеса; официальный сайт датирует альбом 1986 и описывает шире как давление современного мира.',
    'tracks':[
      ('Stereotomy',False,'Внешнее давление режет целостность личности на управляемые слои','Pressure + Repeated cuts = Fragmented self','DO_NOT_CONFUSE_SLICES_WITH_WHOLE'),
      ('Beaujolais',False,'Опьянение и удовольствие как временный обход давления','Pressure + Escape = Temporary relief','ESCAPE_IS_NOT_RESOLUTION'),
      ('Urbania',True,'Город как система потоков, ритмов и обезличивания','City + Density + Process = Urban machine','MAP_THE_SYSTEM_AROUND_THE_SELF'),
      ('Limelight',False,'Слава освещает человека и одновременно лишает приватности','Visibility + Expectation = Identity pressure','LIGHT_CAN_BECOME_PRESSURE'),
      ('In The Real World',False,'Проверка фантазии столкновением с внешними ограничениями','Model + World test = Reality delta','VERIFY_IN_THE_REAL_WORLD'),
      ('Where’s The Walrus?',False,'Абсурдный поиск как маркер дезориентации и смещения критериев','Search + Undefined target = Noise','NAME_THE_TARGET_BEFORE_SEARCH'),
      ('Light Of The World',False,'Свет как ориентация, когда давление фрагментирует человека','Dark pressure + Orienting light = Reassembly','KEEP_A_REFERENCE_LIGHT'),
      ('Chinese Whispers',True,'Передача сообщения по цепочке вносит мутации','Message_0 -> Relay_n = Drift','RELAY_REQUIRES_PROVENANCE'),
      ('Stereotomy Two',False,'Повторное разрезание показывает, что давление не было снято первым проходом','Cut_1 + Return + Cut_2 = Persistent pressure','RECURRING_PRESSURE_NEEDS_ROOT_CAUSE')]
  },
  {
    'album':'Gaudi','year':1987,'slug':'1987-gaudi','official_url':'https://www.the-alan-parsons-project.com/gaudi',
    'official_context':'Inspired by Antoni Gaudí and framed around the work/life balance: devotion to work can crowd out ordinary family life.',
    'user_context':'Финальная студийная работа, вдохновленная жизнью и архитектурой Антонио Гауди.',
    'tracks':[
      ('La Sagrada Familia',False,'Великое незавершённое дело переживает отдельную жизнь создателя','Vision + Generations = Living unfinished work','UNFINISHED_CAN_STILL_BE_ALIVE'),
      ('Too Late',False,'Необратимость упущенного момента','Opportunity - Timely action = Too late','TIME_WINDOW_MATTERS'),
      ('Closer To Heaven',False,'Стремление вверх как поиск смысла за пределами повседневности','Aspiration + Distance = Transcendent orientation','AIM_HIGH_WITHOUT_LEAVING_REALITY'),
      ('Standing On Higher Ground',False,'Высота даёт перспективу, но не отменяет мир внизу','Perspective + Distance = Wider model','HIGHER_VIEW_NEQ_HIGHER_TRUTH'),
      ('Money Talks',False,'Деньги как системный голос, способный подменить человеческие цели','Money + Incentive = Behavioral force','PRICE_NEQ_VALUE'),
      ('Inside Looking Out',False,'Создатель может стать пленником собственного дела и наблюдать жизнь изнутри своей конструкции','Work enclosure + Missed life = Internal exile','CREATION_MUST_NOT_ERASE_CREATOR'),
      ('Paseo De Gracia',True,'Возвращение творения в общественное пространство, где наследие становится маршрутом других','Work + City + Public passage = Shared legacy','LET_THE_WORK_RETURN_TO_THE_WORLD')]
  }
]

def slug(s):
    s=unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode('ascii').lower()
    s=re.sub(r'[^a-z0-9]+','-',s).strip('-')
    return s[:96]

def write_json(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

entries=[]
for album in ALBUMS:
    for i,(title,instrumental,meaning,formula,signal) in enumerate(album['tracks'],1):
        rel=f"{album['slug']}/{i:02d}-{slug(title)}.json"
        obj={
          'schema':'janus.music.track_semantic_analysis.v1',
          'artist':'The Alan Parsons Project',
          'album':album['album'],'album_year':album['year'],'track_number':i,'track_title':title,
          'instrumental_as_official_listing_or_known_album_metadata':instrumental,
          'source_derived':{
            'official_album_page':album['official_url'],
            'official_album_context_paraphrase':album['official_context'],
            'track_membership':'SOURCE_DERIVED_FROM_OFFICIAL_ALBUM_TRACKLIST',
            'user_supplied_context':album['user_context']
          },
          'janus_interpretation':{
            'role':meaning,
            'formula_ru':formula,
            'signal':signal,
            'album_relation':f"Этот трек читается внутри концептуального поля альбома «{album['album']}», а не как изолированное доказательство авторского намерения.",
            'analysis_class':'JANUS_INTERPRETIVE_READING'
          },
          'epistemic_status':{
            'metadata':'SOURCE_DERIVED',
            'album_theme':'SOURCE_DERIVED_PARAPHRASE',
            'track_semantics':'INTERPRETIVE',
            'authorial_intent_for_this_exact_formula':'NOT_CLAIMED'
          },
          'copyright_boundary':{
            'full_lyrics_included':False,
            'literal_lyrics_translation_included':False,
            'method':'metadata + album concept + concise JANUS semantic interpretation'
          },
          'firewall':['TRACK_INTERPRETATION != VERIFIED_AUTHORIAL_INTENT','ALBUM_THEME != CLAIM_THAT_EVERY_TRACK_HAS_ONE_LITERAL_MEANING','MUSICAL_RESONANCE != CAUSAL_MESSAGE']
        }
        write_json(ROOT/rel,obj)
        entries.append({'album':album['album'],'year':album['year'],'track_number':i,'track_title':title,'path':f'data/music/the-alan-parsons-project/{rel}','signal':signal})

index={
 'schema':'janus.music.artist_track_corpus_index.v1',
 'artist':'The Alan Parsons Project',
 'scope':'Original studio-album tracks from Tales of Mystery and Imagination (1976) through Gaudi (1987); bonus tracks excluded.',
 'album_count':len(ALBUMS),'track_json_count':len(entries),
 'sources':[a['official_url'] for a in ALBUMS],
 'year_note':'Official APP site dates Stereotomy to 1986; user prompt listed 1985. Registry preserves the discrepancy rather than silently merging it.',
 'entries':entries,
 'copyright_boundary':'No full lyrics or literal lyric translations are stored.',
 'canonical_seal':'ONE TRACK -> ONE JSON. SOURCE FACTS STAY SOURCE FACTS; JANUS INTERPRETATIONS STAY INTERPRETATIONS.'
}
write_json(ROOT/'INDEX.json',index)
print(f'generated {len(entries)} track JSON files + INDEX')
