from pathlib import Path

PATH=Path('assets/site-curator.js')
s=PATH.read_text(encoding='utf-8')
old="const INAIHR_URL = 'https://hawkar-usls.github.io/iNaiHR/';"
new="const INAIHR_URL = 'https://hawkar-usls.github.io/iNaiHR/janus.html';"
if new not in s:
    if old not in s:
        raise SystemExit('INAIHR_URL anchor changed; refusing unsafe migration')
    s=s.replace(old,new,1)
s=s.replace("inaihr.title = 'iNaiHR · LLM-assisted semantic graph interface';","inaihr.title = 'iNaiHR · semantic SYNTH view of JANUS Meta Registry';")
PATH.write_text(s,encoding='utf-8')
