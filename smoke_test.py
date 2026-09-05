import requests
BASE = 'http://127.0.0.1:8000'
INDUSTRIES = [
    ('9000000001','Pune Foods','Foods@2026'),
    ('9000000011','Pune Pharma','Pharma@2026'),
    ('9000000021','Pune Auto','Auto@2026'),
    ('9000000031','Pune ESDM','Esdm@2026'),
    ('9000000041','Pune Logistics','Logi@2026'),
    ('9000000051','Pune Distillery','Distill@2026'),
    ('9000000061','Pune Renewable Energy','Energy@2026'),
]
failures = 0
for phone, label, pw in INDUSTRIES:
    r = requests.post(BASE + '/auth/login', json={'identifier': phone, 'password': pw})
    if r.status_code != 200:
        print('FAIL', label, r.status_code, r.text[:200])
        failures += 1
        continue
    tok = r.json()['token']
    me = requests.get(BASE + '/profiles/me', headers={'Authorization': 'Bearer ' + tok})
    p = me.json()['profile']
    c = me.json()['checklist']
    sector = p['sector']
    n_appr = len(c['approvals'])
    print('OK  {} demo_id={} sector={} approvals={}'.format(
        label.ljust(28), p.get('registration_no', '-').ljust(16), sector.ljust(18), n_appr))
print('RESULT:', 'ALL PASS' if failures == 0 else '{} FAILURES'.format(failures))
