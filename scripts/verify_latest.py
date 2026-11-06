"""Manual isolated validation; the real pipeline always tests its own candidate."""
import json
import os
import subprocess
import sys
from upstream import fetch,release_identity

release=json.loads(fetch('https://api.github.com/repos/DIYgod/RSSHub/releases/latest'))
tag=release['tag_name']
if release['draft'] or release['prerelease']:raise ValueError('Expected a stable published release')
ref=json.loads(fetch('https://api.github.com/repos/DIYgod/RSSHub/git/ref/tags/'+tag))['object']
while ref['type']=='tag':ref=json.loads(fetch(ref['url']))['object']
if ref['type']!='commit':raise ValueError('Expected Git commit')
sha=ref['sha'];version,image=release_identity(tag,sha)
env={**os.environ,'LAZYCAT_SOURCE_TAG':tag,'LAZYCAT_SOURCE_REVISION':sha,'LAZYCAT_SOURCE_VERSION':version,
    'LAZYCAT_APPLICATION_VERSION':version,'LAZYCAT_OUTPUT_IMAGE':image}
subprocess.run([sys.executable,'-B','scripts/verify_runtime.py'],env=env,check=True)
