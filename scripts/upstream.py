"""Read-only release identity, anonymous OCI inspection and Git changelog."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request

DIGEST = re.compile(r'sha256:[a-f0-9]{64}')
TAG = re.compile(r'v([0-9]{4})\.([0-9]{2})\.([0-9]{2})-([0-9]+)\.([a-f0-9]{7})')
ROOT = Path(__file__).resolve().parents[1]
ACCEPT = ', '.join(('application/vnd.oci.image.index.v1+json','application/vnd.oci.image.manifest.v1+json','application/vnd.docker.distribution.manifest.list.v2+json','application/vnd.docker.distribution.manifest.v2+json'))

def fetch(url, headers=None):
    req=urllib.request.Request(url,headers={'User-Agent':'lazycat-rsshub-adapter/1',**(headers or {})})
    with urllib.request.urlopen(req,timeout=60) as r:data=r.read(16*1024*1024+1)
    if len(data)>16*1024*1024:raise ValueError('Unexpectedly large metadata')
    return data

def release_identity(tag, revision):
    m=TAG.fullmatch(tag)
    if not m or not re.fullmatch('[a-f0-9]{40}',revision) or not revision.startswith(m[5]):
        raise ValueError('Expected exact stable Release tag and matching full commit')
    return f'{int(m[1])}.{int(m[2])}.{int(m[4])}', 'ghcr.io/diygod/rsshub:chromium-bundled-'+revision

def verify_image_config(cfg, revision):
    labels=cfg.get('config',{}).get('Labels',{})
    if cfg.get('os')!='linux' or cfg.get('architecture')!='amd64' or labels.get('org.opencontainers.image.revision')!=revision:
        raise ValueError('Image platform/revision does not match selected Release')
    if not labels.get('org.opencontainers.image.version','').startswith('chromium-bundled'):
        raise ValueError('The selected image does not identify the Chromium variant')

def content_hash(cfg):
    # The official copier adds provenance labels and rewrites the config digest.
    # Compare filesystem diff IDs and all effective runtime settings; ignore
    # only these three well-known non-runtime provenance labels.
    cfg=json.loads(json.dumps(cfg))
    if not cfg.get('rootfs',{}).get('diff_ids'):raise ValueError('Image rootfs identity missing')
    labels=cfg.get('config',{}).get('Labels',{})
    for key in ('cloud.lazycat.image.maintainer','cloud.lazycat.image.origin_hash','cloud.lazycat.image.origin_image'):
        labels.pop(key,None)
    document={k:cfg.get(k) for k in ('os','architecture','rootfs','config')}
    return 'sha256:'+hashlib.sha256(json.dumps(document,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def official_config(reference):
    from static_registry import blob_url
    prefix='registry.lazycat.cloud/'
    if not reference.startswith(prefix):raise ValueError('Expected official runtime image')
    path=reference[len(prefix):]
    if '@' in path:
        digest=path.rsplit('@',1)[1]
    else:
        repo,tag=path.rsplit(':',1)
        if not re.fullmatch(r'[a-z0-9_./-]+',repo) or not re.fullmatch(r'[A-Za-z0-9_.-]+',tag):raise ValueError('Invalid official image path')
        digest=fetch('https://registry-static.lazycat.cloud/docker/registry/v2/repositories/'+repo+'/_manifests/tags/'+tag+'/current/link').decode().strip()
    def read_blob(digest):
        raw=fetch(blob_url(digest))
        if 'sha256:'+hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('Official metadata digest mismatch')
        return json.loads(raw)
    manifest=read_blob(digest)
    return read_blob(manifest['config']['digest'])

def inspect_image(reference):
    host,path=reference.split('/',1)
    repo,tag=(path.split('@',1) if '@' in path else path.rsplit(':',1));repo=repo.rsplit(':',1)[0]
    headers={'Accept':ACCEPT}
    def request(path):
        nonlocal headers
        url='https://'+host+'/v2/'+repo+'/'+path
        try:return fetch(url,headers)
        except urllib.error.HTTPError as e:
            if e.code!=401:raise
            fields=dict(re.findall(r'(\w+)="([^"]*)"',e.headers.get('WWW-Authenticate','')))
            if not fields.get('realm','').startswith('https://'):raise ValueError('Insecure registry authentication endpoint')
            query=urllib.parse.urlencode({'service':fields.get('service',''),'scope':fields.get('scope','repository:'+repo+':pull')})
            token=json.loads(fetch(fields['realm']+'?'+query))
            headers['Authorization']='Bearer '+(token.get('token') or token['access_token'])
            return fetch(url,headers)
    raw=request('manifests/'+tag);document=json.loads(raw)
    if 'manifests' in document:
        matches=[m['digest'] for m in document['manifests'] if m.get('platform',{}).get('os')=='linux' and m.get('platform',{}).get('architecture')=='amd64']
        if len(matches)!=1:raise ValueError('Expected one linux/amd64 image')
        raw=request('manifests/'+matches[0]);document=json.loads(raw)
        if 'sha256:'+hashlib.sha256(raw).hexdigest()!=matches[0]:raise ValueError('Platform manifest digest mismatch')
    digest='sha256:'+hashlib.sha256(raw).hexdigest()
    config_raw=request('blobs/'+document['config']['digest'])
    if 'sha256:'+hashlib.sha256(config_raw).hexdigest()!=document['config']['digest']:raise ValueError('Config digest mismatch')
    return reference.split('@')[0]+'@'+digest, json.loads(config_raw), document

def changelog():
    tag=os.environ['LAZYCAT_SOURCE_TAG'];sha=os.environ['LAZYCAT_SOURCE_REVISION']
    release_identity(tag,sha)
    # Supplied by the executor from its parsed state, including dry-run. This
    # command runs BEFORE prepare installs dependencies: use only stdlib.
    previous=os.environ.get('LAZYCAT_PREVIOUS_SOURCE_REVISION')
    if not previous:previous=json.loads((ROOT/'scripts/baseline.json').read_text())['revision']
    if not re.fullmatch('[a-f0-9]{40}',previous):raise ValueError('Invalid previously processed Git revision')
    with tempfile.TemporaryDirectory(prefix='rsshub-changelog-') as directory:
        def git(*args):return subprocess.check_output(['git','-C',directory,*args],text=True)
        git('init','--bare','--quiet');git('remote','add','origin','https://github.com/DIYgod/RSSHub.git')
        # Only Git objects are downloaded, never the source working tree or an
        # entire CHANGELOG/Release body. Keep the real old→selected commit range.
        git('fetch','--quiet','--filter=blob:none','--no-tags','origin',previous,sha)
        git('merge-base','--is-ancestor',previous,sha)
        count=int(git('rev-list','--count',previous+'..'+sha))
        log=git('log','--no-merges','--format=- %s (%h)','-80',previous+'..'+sha).strip()
    print(f'RSSHub update: {tag}\n\nUpstream changes since {previous[:7]} ({count} commits; up to 80 recent non-merge changes):\n{log}\n\nhttps://github.com/DIYgod/RSSHub/compare/{previous}...{sha}')

if __name__=='__main__':
    if sys.argv[1:]!=['changelog']:raise SystemExit('Use: upstream.py changelog')
    changelog()
