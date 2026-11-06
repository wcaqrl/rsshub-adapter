"""Refuse packaging an untested source/digest or changed deployment."""
import json
import re
from contract import ROOT,CHECKS,load_config,recipe_hash
from upstream import content_hash,official_config

def verify(root=ROOT,read_official=official_config):
    proof=json.loads((root/'.lazycat-action/runtime-proof.json').read_text())
    manifest=root/'lzc-manifest.yml'
    if proof.get('checks')!=CHECKS:raise ValueError('Incomplete runtime checks')
    if proof.get('recipe_sha256')!=recipe_hash(root):raise ValueError('Tested recipe changed')
    if re.findall(r'^\s*# upstream: (\S+)\s*$',manifest.read_text(),re.M)!=[proof['source_ref']]:raise ValueError('Delivered source differs from tested digest')
    cfg=load_config(manifest);package=load_config(root/'package.yml')
    if not cfg['services']['rsshub']['image'].startswith('registry.lazycat.cloud/'):raise ValueError('Official image copy missing')
    if package['package']!='cloud.lazycat.app.rsshub' or package['version']!=proof['application_version']:raise ValueError('Wrong package/version')
    if content_hash(read_official(cfg['services']['rsshub']['image']))!=proof['image_content_sha256']:
        raise ValueError('Official image filesystem/runtime configuration differs from tested image')

if __name__=='__main__':
    verify();print('PASS: tested RSSHub image, package and persistent Redis contract verified.')
