#!/usr/bin/env python3
"""Disposable old→new RSSHub/Redis/Chromium verification on GitHub Runner."""
import base64
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from contract import ROOT,CHECKS,recipe_hash,verify_cache_snapshot
from static_registry import load_baseline
from upstream import release_identity,inspect_image,verify_image_config,content_hash,fetch

def docker(*args, binary=False):
    data=subprocess.check_output(['docker',*args],text=not binary)
    return data if binary else data.strip()

def main():
    tag=os.environ.get('LAZYCAT_SOURCE_TAG') or os.environ['LAZYCAT_SOURCE_REF'].removeprefix('refs/tags/')
    version,reference=release_identity(tag,os.environ['LAZYCAT_SOURCE_REVISION'])
    release=json.loads(fetch('https://api.github.com/repos/DIYgod/RSSHub/releases/tags/'+urllib.parse.quote(tag,safe='')))
    if release['tag_name']!=tag or release['draft'] or release['prerelease']:raise ValueError('Selected tag is not a stable published Release')
    if version!=os.environ['LAZYCAT_SOURCE_VERSION'] or reference!=os.environ['LAZYCAT_OUTPUT_IMAGE']:
        raise ValueError('Executor selected inconsistent source/output')
    pin,cfg,manifest=inspect_image(reference)
    verify_image_config(cfg,os.environ['LAZYCAT_SOURCE_REVISION'])
    docker('pull','--platform','linux/amd64',pin)
    candidate=json.loads(docker('image','inspect',pin))[0]
    if candidate['Id']!=manifest['config']['digest']:raise ValueError('Pulled candidate config differs')
    baseline=json.loads((ROOT/'scripts/baseline.json').read_text())
    old=load_baseline(baseline);redis=load_baseline({'image':baseline['redis_image']})
    proof=ROOT/'.lazycat-action/runtime-proof.json';proof.parent.mkdir(exist_ok=True)
    proof.unlink(missing_ok=True)
    recipe=recipe_hash();prefix='rsshub-ci-'+secrets.token_hex(5)
    network=prefix;app=prefix+'-app';db=prefix+'-redis';fixture=prefix+'-fixture'
    data=Path(tempfile.mkdtemp(prefix='rsshub-redis-'))
    active=[]
    def remove(name):
        if name in active:
            subprocess.run(['docker','stop','--time','20',name],check=True,stdout=subprocess.DEVNULL)
            subprocess.run(['docker','rm','--volumes',name],check=True,stdout=subprocess.DEVNULL)
            active.remove(name)
    def run(name,image,*args,extra=()):
        docker('run','--detach','--name',name,'--network',network,*extra,image,*args);active.append(name)
    def redis_cli(*args,binary=False):return docker('exec',db,'redis-cli','--raw',*args,binary=binary)
    def start_db(directory):
        directory.mkdir(exist_ok=True);directory.chmod(0o777)
        run(db,redis,extra=('--network-alias','redis','--memory','512m','--cpus','1','-v',str(directory)+':/data'))
        for _ in range(60):
            try:
                if redis_cli('PING')=='PONG':return
            except subprocess.CalledProcessError:pass
            time.sleep(1)
        raise RuntimeError('Redis Stack did not start')
    def start_app(image):
        run(app,image,extra=('--memory','2g','--cpus','2','--publish','127.0.0.1::1200',
            '-e','CACHE_TYPE=redis','-e','REDIS_URL=redis://redis:6379','-e','CACHE_EXPIRE=3600',
            '-e','CACHE_CONTENT_EXPIRE=3600','-e','ALLOW_USER_SUPPLY_UNSAFE_DOMAIN=true'))
        port=docker('port',app,'1200/tcp').rsplit(':',1)[1]
        url='http://127.0.0.1:'+port
        for _ in range(150):
            try:
                with urllib.request.urlopen(url+'/healthz',timeout=3) as r:
                    if r.status==200:return url
            except (OSError,urllib.error.URLError):pass
            time.sleep(2)
        raise RuntimeError('RSSHub did not start')
    def feed(url,phase='baseline',cached=False):
        with urllib.request.urlopen(url+'/',timeout=20) as r:assert r.status==200
        target=urllib.parse.quote('http://fixture:8080/items?phase='+phase,safe='')
        rules=urllib.parse.quote('title=RSSHub adapter fixture&itemTitle=title&itemLink=link&itemDesc=description',safe='')
        with urllib.request.urlopen(url+'/rsshub/transform/json/'+target+'/'+rules,timeout=60) as r:
            if cached:assert r.headers.get('RSSHub-Cache-Status')=='HIT','Expected actual cached feed'
            raw=r.read()
        document=ET.fromstring(raw)
        items=document.findall('./channel/item')
        assert len(items)==2 and items[0].findtext('title')=='RSSHub 升级缓存验证', raw[:2000]
        assert items[1].findtext('link')=='https://example.org/two'
        return raw.decode()
    def cache_snapshot():
        keys=[key for key in redis_cli('--scan').splitlines() if key.startswith('rsshub:koa-redis-cache:')]
        return {key:base64.b64encode(redis_cli('DUMP',key,binary=True)).decode() for key in keys}
    def offline_feed(url):
        docker('pause',fixture)
        try:return feed(url,phase='upgrade',cached=True)
        finally:docker('unpause',fixture)
    try:
        docker('network','create',network)
        # Same official Node image hosts a deterministic local upstream. The
        # real RSSHub transformation route produces the feed and Redis cache;
        # test results do not depend on a third-party site/cookie/proxy.
        fixture_js="""require('http').createServer((req,res)=>{res.setHeader('Content-Type','application/json');res.end(JSON.stringify([{title:'RSSHub 升级缓存验证',link:'https://example.org/one',description:'persistent-cache'},{title:'Second item',link:'https://example.org/two',description:'adapter'}]));}).listen(8080,'0.0.0.0');"""
        run(fixture,old,'-e',fixture_js,extra=('--entrypoint','node','--network-alias','fixture','--memory','128m'))
        start_db(data/'upgrade');feed(start_app(old))
        snapshot=cache_snapshot()
        assert snapshot,'RSSHub did not populate its configured Redis feed cache'
        remove(app);assert redis_cli('SAVE')=='OK';remove(db)
        start_db(data/'upgrade')
        verify_cache_snapshot(snapshot,cache_snapshot())
        url=start_app(pin)
        verify_cache_snapshot(snapshot,cache_snapshot())
        report_feed=feed(url,phase='upgrade')
        candidate_snapshot=cache_snapshot()
        verify_cache_snapshot(snapshot,candidate_snapshot)
        assert set(candidate_snapshot)-set(snapshot),'New RSSHub did not write its own Redis feed cache'
        offline_feed(url)
        browser_js="""import fs from 'node:fs';
import {chromium} from 'patchright';
const env=fs.existsSync('/app/.env')?fs.readFileSync('/app/.env','utf8'):'';
const path=process.env.CHROMIUM_EXECUTABLE_PATH || env.match(/^CHROMIUM_EXECUTABLE_PATH=(.+)$/m)?.[1];
const browser=await chromium.launch({headless:true,...(path?{executablePath:path}:{}),args:['--no-sandbox','--disable-dev-shm-usage']});
try { const page=await browser.newPage();await page.setContent('<title>RSSHub Chromium 验证</title><p id="test"></p><script>document.querySelector("#test").textContent=6*7</script>');
if(await page.textContent('#test')!=='42')throw Error('Chromium script failed');console.log(await browser.version());} finally {await browser.close();}"""
        browser_version=docker('exec','--workdir','/app',app,'node','--input-type=module','-e',browser_js)
        remove(app);assert redis_cli('SAVE')=='OK';remove(db)
        start_db(data/'upgrade');verify_cache_snapshot(candidate_snapshot,cache_snapshot())
        url=start_app(pin);offline_feed(url)
        verify_cache_snapshot(snapshot,cache_snapshot());remove(app);remove(db)
        start_db(data/'fresh');feed(start_app(pin))
        assert recipe_hash()==recipe,'Recipe changed during verification'
        result={'source_ref':pin,'revision':os.environ['LAZYCAT_SOURCE_REVISION'],'source_tag':tag,
            'application_version':os.environ['LAZYCAT_APPLICATION_VERSION'],'checks':CHECKS,'recipe_sha256':recipe,
            'baseline_image':baseline['image'],'redis_image':baseline['redis_image'],'image_id':candidate['Id'],
            'cached_keys_verified':len(snapshot),'chromium_version':browser_version,'image_content_sha256':content_hash(cfg)}
        proof.write_text(json.dumps(result,indent=2)+'\n')
        reports=ROOT/'.lazycat-action/reports';reports.mkdir(exist_ok=True)
        (reports/'feed.xml').write_text(report_feed)
        print('PASS: real legacy upgrade, Redis cache persistence, feed generation, Chromium, recreation and fresh install.',flush=True)
        print(json.dumps(result,indent=2),flush=True)
    except BaseException:
        for name in active:
            log=subprocess.run(['docker','logs','--tail','100',name],capture_output=True,text=True)
            print(name,log.stdout,log.stderr)
        raise
    finally:
        for name in list(reversed(active)):remove(name)
        subprocess.run(['docker','network','rm',network],stdout=subprocess.DEVNULL)
        shutil.rmtree(data,ignore_errors=True)

if __name__=='__main__':main()
