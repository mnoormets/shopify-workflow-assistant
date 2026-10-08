import base64
import hashlib
import hmac
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event,select
from sqlalchemy.orm import Session
from backend.api import create_app
from backend.db import StoredOrder
from backend.events import InboxEvent,EventAudit,MAX_BYTES
NOW=datetime(2026,10,8,12,tzinfo=timezone.utc)
SHOP='example-test.myshopify.com'
SECRET='synthetic-test-value-not-a-real-secret'

def payload(**changes):
    result={'id':12345,'created_at':(NOW-timedelta(hours=60)).isoformat(),
        'updated_at':(NOW-timedelta(hours=2)).isoformat(),'financial_status':'pending','fulfillment_status':None,
        'total_price':'42.50','currency':'EUR','line_items':[{'requires_shipping':True}],
        'customer':{'email':'private@example.invalid','first_name':'NEVER STORE THIS'},
        'shipping_address':{'address1':'NEVER STORE THIS'},'note':'NEVER STORE THIS'}
    result.update(changes);return result

def headers(body,event_id=None,shop=SHOP):
    return {'X-Shopify-Hmac-Sha256':base64.b64encode(hmac.new(SECRET.encode(),body,hashlib.sha256).digest()).decode(),
        'X-Shopify-Webhook-Id':event_id or str(uuid4()),'X-Shopify-Shop-Domain':shop,'X-Shopify-Topic':'orders/updated'}

def send(c,data,event_id=None):
    body=json.dumps(data).encode();return c.post('/api/webhooks/shopify',content=body,headers=headers(body,event_id))

@pytest.fixture
def client():
    with TestClient(create_app('sqlite://',clock=lambda:NOW,webhook_secret=SECRET,allowed_shop=SHOP)) as c:yield c

def stored(c):
    with Session(c.app.state.engine) as s:return s.scalars(select(StoredOrder)).all()

def test_ingress_is_durable_but_projection_waits_for_worker(client):
    response=send(client,payload());assert response.status_code==200 and response.json()['status']=='pending'
    assert stored(client)==[]
    outcome=client.post('/api/events/process').json()['outcomes'];assert outcome[0]['outcome']=='processed'
    assert stored(client)[0].payload['financial_status']=='pending'
    assert client.post('/api/events/process').json()['outcomes']==[]

def test_raw_body_hmac_detects_even_whitespace_change(client):
    body=json.dumps(payload()).encode();response=client.post('/api/webhooks/shopify',content=body+b' ',headers=headers(body))
    assert response.status_code==401 and client.get('/api/events').json()['counts']=={}

@pytest.mark.parametrize('signature',['','not base64','AAAA'])
def test_invalid_signature_never_persists(client,signature):
    body=json.dumps(payload()).encode();h=headers(body);h['X-Shopify-Hmac-Sha256']=signature
    assert client.post('/api/webhooks/shopify',content=body,headers=h).status_code==401
    assert client.get('/api/events').json()['events']==[]

def test_configuration_topic_shop_id_and_size_restrictions(client):
    with TestClient(create_app('sqlite://',clock=lambda:NOW)) as c:assert send(c,payload()).status_code==503
    body=json.dumps(payload()).encode()
    for field,value,code in [('X-Shopify-Shop-Domain','other.myshopify.com',403),('X-Shopify-Topic','customers/create',400),('X-Shopify-Webhook-Id','bad',400)]:
        h=headers(body);h[field]=value;assert client.post('/api/webhooks/shopify',content=body,headers=h).status_code==code
    big=b'x'*(MAX_BYTES+1);assert client.post('/api/webhooks/shopify',content=big,headers=headers(big)).status_code==413
    assert client.get('/api/events').json()['events']==[]

def test_duplicate_delivery_and_id_reuse_conflict(client):
    identifier=str(uuid4());data=payload()
    assert send(client,data,identifier).json()['replayed'] is False
    assert send(client,data,identifier).json()['replayed'] is True
    assert send(client,payload(financial_status='paid'),identifier).status_code==409
    client.post('/api/events/process')
    assert send(client,data,identifier).json()['status']=='processed'
    with Session(client.app.state.engine) as s:assert len(s.scalars(select(EventAudit)).all())==1

def test_out_of_order_events_cannot_regress_and_audit_shows_prior_state(client):
    initial=send(client,payload()).json();client.post('/api/events/process')
    newer=send(client,payload(financial_status='paid',updated_at=(NOW-timedelta(hours=1)).isoformat())).json();client.post('/api/events/process')
    old=send(client,payload(updated_at=(NOW-timedelta(hours=3)).isoformat())).json()
    assert client.post('/api/events/process').json()['outcomes'][0]['outcome']=='stale'
    assert stored(client)[0].payload['financial_status']=='paid'
    audit=client.get('/api/events/'+newer['event_id']+'/audit').json()
    assert audit['before']['financial_status']=='pending' and audit['after']['financial_status']=='paid'
    assert client.get('/api/events/'+old['event_id']+'/audit').json()['after']['financial_status']=='paid'

def test_same_timestamp_unchanged_or_conflicting_snapshots(client):
    send(client,payload());client.post('/api/events/process')
    send(client,payload());send(client,payload(financial_status='paid'))
    outcomes=client.post('/api/events/process').json()['outcomes']
    assert {x['outcome'] for x in outcomes}=={'unchanged','conflict'}
    assert stored(client)[0].payload['financial_status']=='pending'

def test_customer_fields_are_not_stored_in_inbox_projection_or_audit(client):
    receipt=send(client,payload()).json();client.post('/api/events/process')
    with Session(client.app.state.engine) as s:
        inbox=s.get(InboxEvent,receipt['event_id'])
        content=json.dumps(inbox.payload)+json.dumps(stored(client)[0].payload)+json.dumps(client.get('/api/events/'+receipt['event_id']+'/audit').json())
        assert 'NEVER STORE THIS' not in content and 'private@example.invalid' not in content
        assert 'customer' not in content and 'shipping_address' not in content
        assert inbox.body_digest==hashlib.sha256(json.dumps(payload()).encode()).hexdigest()

@pytest.mark.parametrize('change',[{'financial_status':'partially_refunded'},{'updated_at':'2026-10-01'}, {'id':True}, {'created_at':'2099-01-01T00:00:00Z'},{'total_price':'not-a-price'},{'line_items':[{'requires_shipping':'no'}]}])
def test_authenticated_invalid_payload_is_retained_as_safe_failure(client,change):
    response=send(client,payload(**change));assert response.status_code==200 and response.json()['status']=='failed'
    client.post('/api/events/process');assert stored(client)==[]
    with Session(client.app.state.engine) as s:
        inbox=s.get(InboxEvent,response.json()['event_id']);assert inbox.payload=={} and inbox.error=='invalid_or_unsupported_order_payload'

def test_failed_transaction_remains_pending_for_safe_retry(client):
    receipt=send(client,payload()).json();engine=client.app.state.engine
    def fail_audit(conn,cursor,statement,parameters,context,executemany):
        if 'INSERT INTO webhook_audit' in statement:raise RuntimeError('Injected storage failure')
    event.listen(engine,'before_cursor_execute',fail_audit)
    with pytest.raises(RuntimeError):client.post('/api/events/process')
    event.remove(engine,'before_cursor_execute',fail_audit)
    assert stored(client)==[]
    assert client.get('/api/events').json()['events'][0]['status']=='pending'
    client.post('/api/events/process');assert len(stored(client))==1
    assert client.get('/api/events/'+receipt['event_id']+'/audit').status_code==200

def test_external_observations_survive_and_no_carrier_handover_is_invented(client):
    send(client,payload());client.post('/api/events/process');order=stored(client)[0].payload
    assert order['shipment_status']=='unknown'
    order.update(provider_status='paid',stock_status='insufficient',shipment_status='handed_over')
    client.post('/api/import',json={'orders':[order]},headers={'Idempotency-Key':'external-observation'})
    send(client,payload(financial_status='paid',updated_at=(NOW-timedelta(hours=1)).isoformat()));client.post('/api/events/process')
    result=stored(client)[0].payload
    assert result['provider_status']=='paid' and result['stock_status']=='insufficient' and result['shipment_status']=='handed_over'

def test_inbox_survives_restart_and_duplicate_is_still_ignored(tmp_path):
    url=f"sqlite:///{tmp_path/'events.db'}";identifier=str(uuid4())
    with TestClient(create_app(url,clock=lambda:NOW,webhook_secret=SECRET,allowed_shop=SHOP)) as c:send(c,payload(),identifier)
    with TestClient(create_app(url,clock=lambda:NOW,webhook_secret=SECRET,allowed_shop=SHOP)) as c:
        assert send(c,payload(),identifier).json()['replayed'] is True
        assert len(c.post('/api/events/process').json()['outcomes'])==1
        assert len(stored(c))==1

def test_concurrent_duplicate_delivery_file_database(tmp_path):
    app=create_app(f"sqlite:///{tmp_path/'concurrent.db'}",clock=lambda:NOW,webhook_secret=SECRET,allowed_shop=SHOP)
    identifier=str(uuid4())
    with TestClient(app) as c:
        with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(lambda _:send(c,payload(),identifier),range(8)))
        assert all(r.status_code==200 for r in results)
        assert sum(not r.json()['replayed'] for r in results)==1
        assert len(c.get('/api/events').json()['events'])==1

def test_simulator_replays_without_new_events_and_is_disabled_for_real_receiver():
    current=[NOW]
    with TestClient(create_app('sqlite://',clock=lambda:current[0])) as c:
        first=c.post('/api/integration-demo');assert first.status_code==200
        assert [x['outcome'] for x in first.json()['outcomes']]==['processed','processed','stale']
        assert first.json()['receipts'][-1]['replayed'] is True
        current[0]+=timedelta(hours=1)
        again=c.post('/api/integration-demo');assert again.status_code==200 and again.json()['outcomes']==[]
        assert len(c.get('/api/events').json()['events'])==3
        assert stored(c)[0].payload['financial_status']=='paid'
    with TestClient(create_app('sqlite://',clock=lambda:NOW,webhook_secret=SECRET,allowed_shop=SHOP)) as c:
        assert c.post('/api/integration-demo').status_code==403
