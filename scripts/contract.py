"""Hash the tested deployment semantically, allowing only delivery/version edits."""
import hashlib
import json
from pathlib import Path
import yaml

ROOT=Path(__file__).resolve().parents[1]
CHECKS=['baseline-feed','baseline-redis-cache','upgrade-feed','upgrade-redis-cache','redis-persistence','chromium','container-recreation','fresh-install']

def verify_cache_snapshot(snapshot,current):
    if not snapshot or any(current.get(key)!=value for key,value in snapshot.items()):
        raise ValueError('Actual RSSHub feed cache was lost or modified')

def load_config(path):
    value=yaml.safe_load(path.read_text())
    if not isinstance(value,dict):raise ValueError('Expected YAML mapping')
    return value

def recipe_hash(root=ROOT):
    paths=[root/n for n in ('lzc-manifest.yml','package.yml','lzc-build.yml','icon.png')]
    paths += [p for p in (root/'scripts').rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc']
    result=hashlib.sha256()
    for path in sorted(paths):
        raw=path.read_bytes()
        if path.name in ('lzc-manifest.yml','package.yml'):
            doc=load_config(path)
            if path.name=='package.yml':doc['version']='<allocated-version>'
            else:doc['services']['rsshub']['image']='<delivered-image>'
            raw=json.dumps(doc,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()
        result.update(str(path.relative_to(root)).encode()+b'\0'+raw+b'\0')
    return result.hexdigest()
