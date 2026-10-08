from datetime import datetime,timezone
from fastapi.testclient import TestClient
from backend.api import create_app
import pytest
NOW=datetime(2026,10,8,10,tzinfo=timezone.utc)
@pytest.fixture
def client():
    with TestClient(create_app('sqlite://',clock=lambda:NOW)) as c:
        c.post('/api/demo');yield c

def first(client):
    client.post('/api/incidents/sync')
    return client.get('/api/incidents').json()['incidents'][0]

def edit(row,**changes):
    return {'revision':row['revision'],'status':'investigating','owner':'demo-operator','actor':'demo-operator','note':'Checked the evidence.',**changes}

def test_sync_idempotent_and_audit_has_source_snapshot(client):
    assert client.post('/api/incidents/sync').json()['created']==8
    assert client.post('/api/incidents/sync').json()['created']==0
    row=first(client);d=client.get('/api/incidents/'+row['incident_id']).json()
    assert len(d['history'])==1 and d['history'][0]['after']['finding']==row['finding']

def test_revision_conflict_does_not_overwrite_or_append_history(client):
    row=first(client);path='/api/incidents/'+row['incident_id']
    updated=client.patch(path,json=edit(row)).json()
    assert updated['revision']==2 and updated['status']=='investigating'
    assert [r['revision'] for r in client.get(path).json()['history']]==[1,2]
    assert client.patch(path,json=edit(row,status='dismissed')).status_code==409
    d=client.get(path).json();assert d['incident']['status']=='investigating' and len(d['history'])==2

def test_resolution_requires_investigation_and_reopens_explicitly(client):
    row=first(client);path='/api/incidents/'+row['incident_id']
    assert client.patch(path,json=edit(row,status='resolved')).status_code==422
    row=client.patch(path,json=edit(row)).json()
    row=client.patch(path,json=edit(row,status='resolved',note='Operator recorded outcome.')).json()
    assert row['active'] and row['status']=='resolved'
    client.post('/api/incidents/sync')
    assert client.get(path).json()['incident']['status']=='resolved'
    assert client.patch(path,json=edit(row,status='investigating')).status_code==200

@pytest.mark.parametrize('changes',[{'actor':' '},{'note':' '},{'revision':True},{'revision':0},{'status':'refunded'},{'note':'x'*1001}])
def test_invalid_operator_edits_rejected(client,changes):
    row=first(client)
    assert client.patch('/api/incidents/'+row['incident_id'],json=edit(row,**changes)).status_code==422

def test_cleared_detection_does_not_fabricate_operator_resolution(client):
    first(client)
    original=client.get('/api/incidents?q=DEMO-001').json()['incidents']
    # Raising the threshold clears only the age finding; stock shortage remains.
    client.put('/api/policy',json={'paid_unfulfilled_hours':720,'pending_payment_hours':24})
    client.post('/api/incidents/sync')
    rows=client.get('/api/incidents?q=DEMO-001').json()['incidents']
    age=next(r for r in rows if r['code']=='PAID_NOT_FULFILLED')
    assert age['active'] is False and age['status']=='open'
    client.put('/api/policy',json={'paid_unfulfilled_hours':48,'pending_payment_hours':24})
    client.post('/api/incidents/sync')
    assert next(r for r in client.get('/api/incidents?q=DEMO-001').json()['incidents'] if r['code']=='PAID_NOT_FULFILLED')['active']

def test_listing_limits_filters_and_literal_wildcards(client):
    first(client)
    assert client.get('/api/incidents?limit=1').json()['has_more']
    assert client.get('/api/incidents?q=%25').json()['incidents']==[]
    assert client.get('/api/incidents?status=bad').status_code==422
    assert client.get('/api/incidents/missing').status_code==404


def test_realistic_scenario_import_is_repeatable_and_clean_groups_stay_clean(client):
    result=client.post('/api/scenario')
    assert result.status_code==200 and result.json()['imported']==120
    assert client.post('/api/scenario').json()['replayed'] is True
    findings=client.get('/api/findings?q=SCENARIO').json()['findings']
    assert len(findings)==105
    assert all(int(f['order_id'].split('-')[1])%8<5 for f in findings)
    client.post('/api/incidents/sync')
    listing=client.get('/api/incidents?q=SCENARIO&limit=200').json()
    assert len(listing['incidents'])==105 and not listing['has_more']


def test_existing_audit_schema_upgraded_without_losing_notes(tmp_path):
    import sqlite3,json
    from sqlalchemy import inspect,text
    path=tmp_path/'legacy.db'
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE incident_audit (audit_id TEXT PRIMARY KEY, incident_id TEXT, timestamp TEXT, actor TEXT, action TEXT, note TEXT, before JSON, after JSON)')
        connection.execute('INSERT INTO incident_audit VALUES (?,?,?,?,?,?,?,?)',('legacy','case','2026-01-01','operator','operator_update','preserve this note','{}',json.dumps({'revision':3})))
    application=create_app('sqlite:///'+str(path),clock=lambda:NOW)
    assert 'revision' in {c['name'] for c in inspect(application.state.engine).get_columns('incident_audit')}
    with application.state.engine.connect() as connection:
        row=connection.execute(text('SELECT note,revision FROM incident_audit WHERE audit_id=\'legacy\'')).one()
        assert tuple(row)==('preserve this note',3)
    application.state.engine.dispose()
