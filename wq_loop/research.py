#!/usr/bin/env python3
"""Read-only catalog/history queries and local candidate precheck; no network/auth."""
import importlib.util,json,sys
from pathlib import Path
R=Path(__file__).resolve().parent;H=R.parent/'wq_harness'
def read(p):return json.loads(p.read_text())
cmd=sys.argv[1]
if cmd=='categories':
    print(json.dumps({k:len(v) for k,v in read(H/'fields_cache/categories.json').items()},indent=2))
elif cmd=='fields':
    category=sys.argv[2];word=sys.argv[3].lower() if len(sys.argv)>3 else ''
    ids=read(H/'fields_cache/categories.json').get(category,[])
    catalog=read(R/'catalog.json')
    def rows(x):
        if isinstance(x,list):
            for y in x:yield from rows(y)
        elif isinstance(x,dict):
            if 'id' in x:yield x
            else:
                for v in x.values():yield from rows(v)
    actual={x['id']:x for x in rows(catalog)}
    matches=[actual[i] for i in ids if i in actual and (not word or word in json.dumps(actual[i]).lower())]
    print(json.dumps(matches[:15],indent=2));print('Returned',min(len(matches),15),'of',len(matches),'confirmed fields')
elif cmd=='memory':
    word=sys.argv[2].lower() if len(sys.argv)>2 else ''
    matches=[]
    for line in (H/'memory.jsonl').read_text().splitlines():
        try:x=json.loads(line)
        except ValueError:continue
        if not word or word in line.lower():matches.append({k:x.get(k) for k in ('expression','category','hypothesis','sharpe','fitness','turnover','checks','checks_failed','overall','submitted')})
    print(json.dumps({'total_matches':len(matches),'latest':matches[-8:]},indent=2))
elif cmd=='precheck':
    spec=importlib.util.spec_from_file_location('engine',R/'engine.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    print(json.dumps([{'i':i,**m.strictcheck(x.get('fast_expression') or x.get('expression') or '')} for i,x in enumerate(read(Path(sys.argv[2])))],indent=2))
else:raise SystemExit('Allowed: categories | fields CATEGORY KEYWORD | memory KEYWORD | precheck FILE')
