import json
from datetime import datetime,timedelta,timezone
from pathlib import Path
import httpx
import pytest
from fastapi.testclient import TestClient
from backend.api import create_app
from backend.domain import Order,ReviewPolicy,evaluate
NOW=datetime(2026,10,8,10,tzinfo=timezone.utc)
ROOT=Path(__file__).resolve().parents[1]

def row(**changes):
    data = dict(order_id="A",created_at=(NOW-timedelta(hours=60)).isoformat(),financial_status="paid",fulfillment_status="unfulfilled",total="10.00",currency="EUR")
    data.update(changes)
    return data
@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("SHOPIFY_OPS_MODEL",raising=False)
    with TestClient(create_app("sqlite://",clock=lambda:NOW)) as c:yield c

def test_demo_ground_truth_and_clean_orders(client):
    assert client.post('/api/demo').status_code==200
    r=client.get('/api/findings').json()
    assert r['orders_scanned']==8
    assert {(f['order_id'],f['code']) for f in r['findings']}=={('DEMO-001','PAID_NOT_FULFILLED'),('DEMO-001','STOCK_SHORTAGE'),('DEMO-002','PAYMENT_PENDING'),('DEMO-003','REFUNDED_FULFILLED'),('DEMO-004','TRACKING_MISSING'),('DEMO-005','PAYMENT_PENDING'),('DEMO-005','PAYMENT_MISMATCH'),('DEMO-005','SHIPMENT_MISMATCH')}
    assert client.get('/api/findings?q=DEMO-006').json()['findings']==[]
    assert client.get('/api/findings?q=DEMO-007').json()['findings']==[]
    assert client.get('/api/findings?q=DEMO-008').json()['findings']==[]

def test_idempotency_does_not_duplicate_or_overwrite_on_conflict(client):
    payload={'orders':[row()]};headers={'Idempotency-Key':'batch'}
    assert client.post('/api/import',json=payload,headers=headers).json()['replayed'] is False
    assert client.post('/api/import',json=payload,headers=headers).json()['replayed'] is True
    payload['orders'][0]['financial_status']='pending'
    assert client.post('/api/import',json=payload,headers=headers).status_code==409
    assert client.get('/api/findings').json()['orders_scanned']==1
    assert client.get('/api/findings').json()['findings'][0]['code']=='PAID_NOT_FULFILLED'

def test_new_import_updates_existing_order_without_duplicating(client):
    first=row();client.post('/api/import',json={'orders':[first]},headers={'Idempotency-Key':'a'})
    first['fulfillment_status']='fulfilled';first['tracking_number']='TEST'
    client.post('/api/import',json={'orders':[first]},headers={'Idempotency-Key':'b'})
    assert client.get('/api/findings').json()['orders_scanned']==1
    assert client.get('/api/findings').json()['findings']==[]

@pytest.mark.parametrize('change',[{'created_at':'2026-10-01T00:00:00'},{'created_at':'2099-01-01T00:00:00Z'},{'total':'NaN'},{'total':'-1'},{'currency':'eu'},{'financial_status':'garbage'},{'customer_email':'private@example.com'},{'total':'10.001'}])
def test_invalid_batch_is_atomic(client,change):
    bad=row();bad.update(change);bad['order_id']='B'
    r=client.post('/api/import',json={'orders':[row(),bad]},headers={'Idempotency-Key':'invalid'})
    assert r.status_code==422
    assert client.get('/api/findings').json()['orders_scanned']==0

def test_duplicate_ids_and_missing_key_rejected(client):
    assert client.post('/api/import',json={'orders':[row(),row()]},headers={'Idempotency-Key':'x'}).status_code==422
    assert client.post('/api/import',json={'orders':[row()]}).status_code==422

@pytest.mark.parametrize('hours,expected',[(47.999,False),(48,True),(48.001,True)])
def test_paid_threshold_boundary(hours,expected):
    data=row();data['created_at']=(NOW-timedelta(hours=hours)).isoformat()
    assert bool(evaluate(Order.model_validate(data),NOW))==expected

def test_filters_and_rule_explanation(client):
    client.post('/api/demo')
    found=client.get('/api/findings?q=DEMO-001&severity=high').json()
    assert len(found['findings'])==2
    assert client.get('/api/findings?severity=bad').status_code==422
    r=client.post('/api/explain/DEMO-001/STOCK_SHORTAGE').json()
    assert r['source']=='rules'
    assert client.post('/api/explain/unknown/unknown').status_code==404

def test_persistence_after_restart(tmp_path,monkeypatch):
    monkeypatch.delenv('SHOPIFY_OPS_MODEL',raising=False)
    url=f"sqlite:///{tmp_path/'orders.db'}"
    with TestClient(create_app(url,clock=lambda:NOW)) as c:c.post('/api/demo')
    with TestClient(create_app(url,clock=lambda:NOW)) as c:assert c.get('/api/findings').json()['orders_scanned']==8

def test_local_ai_receives_only_finding_and_uses_valid_response(monkeypatch):
    monkeypatch.setenv('SHOPIFY_OPS_MODEL','test-model')
    def handler(request):
        data=json.loads(request.content)
        assert request.url.host=='127.0.0.1'
        assert data['stream'] is False
        facts=json.loads(data['messages'][1]['content'])
        assert set(facts)=={'code','reason','suggested_action','evidence'}
        return httpx.Response(200,json={'message':{'content':json.dumps({'explanation':'Kontrolli makseolekuid.','checks':['Võrdle pakkuja ja poe olekut.']})}})
    with TestClient(create_app('sqlite://',clock=lambda:NOW,ai_transport=httpx.MockTransport(handler))) as c:
        c.post('/api/demo');r=c.post('/api/explain/DEMO-005/PAYMENT_MISMATCH').json()
        assert r['source']=='local_ai'

@pytest.mark.parametrize('response',[httpx.Response(503),httpx.Response(200,json={'message':{'content':'not json'}})])
def test_ai_failure_falls_back_without_losing_evidence(monkeypatch,response):
    monkeypatch.setenv('SHOPIFY_OPS_MODEL','test-model')
    with TestClient(create_app('sqlite://',clock=lambda:NOW,ai_transport=httpx.MockTransport(lambda req:response))) as c:
        c.post('/api/demo');before=c.get('/api/findings').json()
        assert c.post('/api/explain/DEMO-005/PAYMENT_MISMATCH').json()['source']=='rules_fallback'
        assert c.get('/api/findings').json()==before


@pytest.mark.parametrize("status,field,code", [
    ("paid", "paid_unfulfilled_hours", "PAID_NOT_FULFILLED"),
    ("pending", "pending_payment_hours", "PAYMENT_PENDING"),
])
@pytest.mark.parametrize("minutes,expected", [(179,False),(180,True),(181,True)])
def test_custom_policy_exact_minute_boundary(status,field,code,minutes,expected):
    policy=ReviewPolicy(**{field:3})
    order=Order.model_validate(row(financial_status=status,created_at=(NOW-timedelta(minutes=minutes)).isoformat()))
    findings=evaluate(order,NOW,policy)
    assert (code in {f.code for f in findings}) is expected
    if expected:
        assert findings[0].evidence['threshold_hours']=='3'
        assert '3 hours' in findings[0].reason

@pytest.mark.parametrize('value',[0,-1,721,1.5,True,'24',None])
def test_invalid_policy_cannot_replace_saved_settings(client,value):
    valid={'paid_unfulfilled_hours':72,'pending_payment_hours':12}
    assert client.put('/api/policy',json=valid).status_code==200
    assert client.put('/api/policy',json={**valid,'paid_unfulfilled_hours':value}).status_code==422
    assert client.get('/api/policy').json()==valid

def test_policy_recalculates_without_changing_imported_orders(client):
    client.post('/api/import',json={'orders':[row(provider_status='pending')]},headers={'Idempotency-Key':'policy-test'})
    assert {f['code'] for f in client.get('/api/findings').json()['findings']}=={'PAID_NOT_FULFILLED','PAYMENT_MISMATCH'}
    policy={'paid_unfulfilled_hours':72,'pending_payment_hours':24}
    client.put('/api/policy',json=policy)
    report=client.get('/api/findings').json()
    assert report['orders_scanned']==1 and report['policy']==policy
    assert {f['code'] for f in report['findings']}=={'PAYMENT_MISMATCH'}
    assert client.post('/api/explain/A/PAID_NOT_FULFILLED').status_code==404
    client.put('/api/policy',json={**policy,'paid_unfulfilled_hours':48})
    assert len(client.get('/api/findings').json()['findings'])==2

def test_policy_survives_restart(tmp_path):
    url=f"sqlite:///{tmp_path/'settings.db'}"
    policy={'paid_unfulfilled_hours':96,'pending_payment_hours':72}
    with TestClient(create_app(url,clock=lambda:NOW)) as c:
        c.post('/api/import',json={'orders':[row(financial_status='pending')]},headers={'Idempotency-Key':'persist'});assert c.put('/api/policy',json=policy).status_code==200
    with TestClient(create_app(url,clock=lambda:NOW)) as c:
        assert c.get('/api/policy').json()==policy
        assert 'PAYMENT_PENDING' not in {f['code'] for f in c.get('/api/findings').json()['findings']}
