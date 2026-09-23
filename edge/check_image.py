"""CI only: local portal container. No provider request or database access."""
import time
import urllib.error
import urllib.request

BASE='http://127.0.0.1:8081'
KEY='s'*43

def get(path,headers=None):
    try:
        with urllib.request.urlopen(urllib.request.Request(BASE+path,headers=headers or {}),timeout=3) as response:
            return response.status,response.headers,response.read().decode()
    except urllib.error.HTTPError as response:
        return response.code,response.headers,response.read().decode()

for _ in range(30):
    try:
        status,headers,body=get('/auth/login',{'X-Richon-Edge-Key':KEY})
        if status==200:break
    except OSError:pass
    time.sleep(1)
else:raise SystemExit('Portal did not become ready')
assert '카카오로 로그인' in body and 'synthetic' not in body
assert headers['Cache-Control']=='no-store'
assert 'HttpOnly' in headers['Set-Cookie'] and 'Domain=' not in headers['Set-Cookie']
assert get('/auth/login')[0]==403
for path in ['/orders','/health/db','/docs','/openapi.json']:
    assert get(path,{'X-Richon-Edge-Key':KEY})[0]==404
assert get('/portal/api/admin/summary',{'X-Richon-Edge-Key':KEY})[0]==401
print('PASS: gated portal image; private paths absent; no DB/provider network')
