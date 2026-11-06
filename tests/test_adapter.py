import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import upstream
import contract
import verify_package


class ReleaseTests(unittest.TestCase):
    def test_release_maps_to_exact_full_commit_chromium_image(self):
        sha = '4be79cd40cae69ce68b7837f927b63cdab7be719'
        tag = 'v2026.11.06-8596.4be79cd'
        self.assertEqual(upstream.release_identity(tag, sha), ('2026.11.8596', 'ghcr.io/diygod/rsshub:chromium-bundled-' + sha))

    def test_rejects_unrelated_commit_and_prereleases(self):
        for tag, sha in [('v2026.11.06-8596.1111111', 'a'*40), ('v2026.11.06-8596.aaaaaaa-beta', 'a'*40), ('latest', 'a'*40)]:
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                upstream.release_identity(tag, sha)

    def test_image_identity_requires_revision_and_browser_variant(self):
        sha='a'*40
        cfg={'os':'linux','architecture':'amd64','config':{'Labels':{'org.opencontainers.image.revision':sha,'org.opencontainers.image.version':'chromium-bundled-'+sha}}}
        upstream.verify_image_config(cfg,sha)
        for field,value in [('architecture','arm64'),('os','windows')]:
            bad=json.loads(json.dumps(cfg));bad[field]=value
            with self.assertRaises(ValueError):upstream.verify_image_config(bad,sha)
        cfg['config']['Labels']['org.opencontainers.image.revision']='b'*40
        with self.assertRaises(ValueError):upstream.verify_image_config(cfg,sha)

    def test_official_labels_may_change_but_image_contents_must_match(self):
        cfg={'os':'linux','architecture':'amd64','rootfs':{'diff_ids':['sha256:'+'a'*64]},'config':{'Env':['CACHE_TYPE=redis'],'Labels':{'app':'rsshub'}}}
        expected=upstream.content_hash(cfg)
        copied=json.loads(json.dumps(cfg));copied['config']['Labels']['cloud.lazycat.image.maintainer']='Peter'
        self.assertEqual(expected,upstream.content_hash(copied))
        copied['config']['Env']=['CACHE_TYPE=memory']
        self.assertNotEqual(expected,upstream.content_hash(copied))

    def test_legacy_real_feed_cache_must_survive_candidate_use(self):
        snapshot={'rsshub:koa-redis-cache:old-feed':'cached-feed-bytes'}
        contract.verify_cache_snapshot(snapshot,{**snapshot,'rsshub:koa-redis-cache:new-feed':'new-feed-bytes'})
        for changed in ({},{'rsshub:koa-redis-cache:old-feed':'different'}):
            with self.assertRaises(ValueError):contract.verify_cache_snapshot(snapshot,changed)

    def test_upgrade_baseline_advances_to_previous_delivered_image(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'scripts').mkdir()
            baseline=json.loads((ROOT/'scripts/baseline.json').read_text())
            (root/'scripts/baseline.json').write_text(json.dumps(baseline))
            self.assertEqual(upstream.upgrade_baseline(root)['image'],baseline['image'])
            runtime='registry.lazycat.cloud/peter/diygod/rsshub:previous'
            lock={'status':'submitted','application':{'package':'cloud.lazycat.app.rsshub','version':'2026.11.8596'},'source':{'kind':'git','revision':'a'*40},'images':[{'id':'rsshub','runtime_ref':runtime}]}
            (root/'.lazycat-action.lock.yml').write_text(json.dumps(lock))
            expected=runtime+'@sha256:'+'b'*64
            chosen=upstream.upgrade_baseline(root,pin_official=lambda ref:expected)
            self.assertEqual(chosen['image'],expected)
            self.assertEqual(chosen['revision'],'a'*40)
            self.assertEqual(chosen['redis_image'],baseline['redis_image'])
            lock['images'][0]['runtime_ref']='untrusted.example/rsshub:previous'
            (root/'.lazycat-action.lock.yml').write_text(json.dumps(lock))
            with self.assertRaises(ValueError):upstream.upgrade_baseline(root,pin_official=lambda ref:expected)


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        for name in ('lzc-manifest.yml','lzc-build.yml','package.yml','icon.png'):
            shutil.copyfile(ROOT/name,self.root/name)
        shutil.copytree(ROOT/'scripts',self.root/'scripts')
        self.source='ghcr.io/diygod/rsshub:chromium-bundled-'+'a'*40+'@sha256:'+'b'*64
        self.config={'os':'linux','architecture':'amd64','rootfs':{'diff_ids':['sha256:'+'d'*64]},'config':{'Env':['CACHE_TYPE=redis']}}
        self.proof={'source_ref':self.source,'revision':'a'*40,'checks':contract.CHECKS,'recipe_sha256':contract.recipe_hash(self.root),'application_version':contract.load_config(self.root/'package.yml')['version'],'image_content_sha256':upstream.content_hash(self.config)}
        p=self.root/'.lazycat-action';p.mkdir()
        (p/'runtime-proof.json').write_text(json.dumps(self.proof))
        path=self.root/'lzc-manifest.yml';cfg=contract.load_config(path)
        cfg['services']['rsshub']['image']='registry.lazycat.cloud/peter/rsshub:test'
        import yaml
        path.write_text('# upstream: '+self.source+'\n'+yaml.safe_dump(cfg,allow_unicode=True,sort_keys=False))

    def test_exact_tested_delivery_is_accepted(self):
        verify_package.verify(self.root,read_official=lambda ref:self.config)

    def test_unrelated_official_image_with_same_upstream_comment_is_rejected(self):
        cfg=json.loads(json.dumps(self.config));cfg['rootfs']['diff_ids']=['sha256:'+'e'*64]
        with self.assertRaises(ValueError):verify_package.verify(self.root,read_official=lambda ref:cfg)

    def test_tampered_image_or_configuration_is_rejected(self):
        p=self.root/'lzc-manifest.yml';original=p.read_text()
        p.write_text(original.replace(self.source,self.source[:-1]+'c'))
        with self.assertRaises(ValueError):verify_package.verify(self.root)
        p.write_text(original.replace('/lzcapp/var/redis','/lzcapp/var/other'))
        with self.assertRaises(ValueError):verify_package.verify(self.root)

    def test_missing_runtime_check_is_rejected(self):
        self.proof['checks']=contract.CHECKS[:-1]
        (self.root/'.lazycat-action/runtime-proof.json').write_text(json.dumps(self.proof))
        with self.assertRaises(ValueError):verify_package.verify(self.root)


if __name__=='__main__':unittest.main()
