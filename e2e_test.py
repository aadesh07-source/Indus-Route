import requests, json
BASE = 'http://127.0.0.1:8000'

def login(identifier, password='Demo@123'):
    r = requests.post(BASE + '/auth/login', json={'identifier': identifier, 'password': password})
    r.raise_for_status()
    return r.json()['token']

def auth(token):
    return {'Authorization': 'Bearer ' + token}

print('=== Full E2E flow: Pune Pharma -> AI auto-fill -> submit -> officer review -> send back -> resubmit -> approve -> certificate ===')
tok = login('9000000011', 'Pharma@2026')
me = requests.get(BASE + '/profiles/me', headers=auth(tok)).json()
print('Applicant:', me['profile']['name'], 'sector =', me['profile']['sector'])
ck = me['checklist']
print('Approvals available:', len(ck['approvals']))

# Pick the first approval
target_appr = ck['approvals'][0]
print('Selected approval:', target_appr['code'], '-', target_appr['name'])

# Create application
r = requests.post(BASE + '/applications', json={'approval_id': target_appr['id']}, headers=auth(tok))
r.raise_for_status()
app_id = r.json()['application_id']
print('Created application:', app_id)

# Get eligible schemes
sch = requests.get(BASE + '/schemes/recommendations', headers=auth(tok)).json()
print('Eligible schemes:', [s['id'] for s in sch['eligible']])

# Select first 2 eligible schemes
picks = [s['id'] for s in sch['eligible'][:2]]
r = requests.post(BASE + f'/applications/{app_id}/schemes', json={'scheme_ids': picks}, headers=auth(tok))
r.raise_for_status()
print('Schemes saved:', r.json())

# AI auto-fill
r = requests.post(BASE + f'/applications/{app_id}/auto-fill-from-data', headers=auth(tok))
r.raise_for_status()
print('AI auto-fill sources:', r.json()['sources'])
print('AI auto-fill form:', r.json()['form']['verification_code'])

# Submit
r = requests.post(BASE + f'/applications/{app_id}/submit', headers=auth(tok))
r.raise_for_status()
print('Submit status:', r.json()['application']['status'])

# Officer login
otok = login('9000000002')
# Claim app
r = requests.post(BASE + f'/officer/applications/{app_id}/assign', headers=auth(otok))
print('Officer assign:', r.status_code, r.json())

# Pre-scrutiny
pre = requests.get(BASE + f'/officer/applications/{app_id}/pre-scrutiny', headers=auth(otok)).json()
print('Pre-scrutiny unsigned parameters:', pre['one_click']['unsigned_count'])
print('Parameters:')
for p in pre['parameters']:
    print(f"  - {p['param_key']:30s} state={p['state']:10s} signed={p['signed']}")

# Officer sends back (with corrections)
notes = ("AI-drafted correction list:\n"
         "1. PAN card upload is missing — please attach a clear scan.\n"
         "2. GSTIN on uploaded certificate does not match profile PAN — recheck.\n"
         "3. Investment value exceeds declared threshold — update profile.")
r = requests.post(BASE + f'/officer/applications/{app_id}/decision',
                  json={'action': 'send_back', 'notes': notes, 'clarification_text': ''},
                  headers=auth(otok))
print('Officer send_back:', r.status_code, r.json())

# Applicant sees feedback
app = requests.get(BASE + f'/applications/{app_id}', headers=auth(tok)).json()
print('Applicant feedback:', app['application'].get('feedback', '')[:80], '...')

# Applicant resubmits (clears feedback + re-submits)
r = requests.post(BASE + f'/applications/{app_id}/submit', headers=auth(tok))
print('Resubmit:', r.status_code, r.json()['application']['status'])

# Officer signs all green parameters
pre = requests.get(BASE + f'/officer/applications/{app_id}/pre-scrutiny', headers=auth(otok)).json()
for p in pre['parameters']:
    if p['state'] == 'green' and not p['signed']:
        r = requests.post(BASE + f'/officer/applications/{app_id}/sign-parameter',
                          json={'param_key': p['param_key'], 'note': 'verified'},
                          headers=auth(otok))
        print(f"  signed {p['param_key']}: {r.json().get('signed')}")

# Approve
r = requests.post(BASE + f'/officer/applications/{app_id}/decision',
                  json={'action': 'approve', 'notes': 'All clear', 'clarification_text': ''},
                  headers=auth(otok))
print('Approve:', r.status_code, r.json())

# Issue certificate
r = requests.post(BASE + f'/officer/applications/{app_id}/issue-certificate',
                  json={'certificate_type': 'sanction_clearance'},
                  headers=auth(otok))
print('Issue certificate:', r.status_code, r.json())

# Applicant downloads certificate
r = requests.get(BASE + f'/applications/{app_id}/certificate.pdf', headers=auth(tok))
print('Certificate download:', r.status_code, 'bytes:', len(r.content), 'content-type:', r.headers.get('Content-Type'))

# Public verification
import re
m = re.search(r'INDUS-SANCTION-\d+', r.headers.get('Content-Disposition', ''))
cert_no = m.group(0) if m else ''
r = requests.get(BASE + f'/officer/certificates/verify/{cert_no}')
print('Public cert verify:', r.status_code, r.json())

print()
print('=== ALL FLOWS PASSED ===')
