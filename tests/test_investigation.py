"""Behavioral checks: malicious output cannot introduce facts or store actions."""
import json
from datetime import datetime,timezone
import httpx,pytest
from fastapi.testclient import TestClient
from backend.api import create_app

NOW=datetime(2026,10,9,tzinfo=timezone.utc)

def setup(monkeypatch,output=None):
    monkeypatch.delenv('SHOPIFY_OPS_MODEL',raising=False)
    transport=None
    if output is not None:
        monkeypatch.setenv('SHOPIFY_OPS_MODEL','fixture-not-a-real-model')
        def handler(request):
            payload=json.loads(request.content)
            facts=json.loads(payload['messages'][1]['content'])
            assert set(facts)=={'evidence','steps'}
            assert 'order_id' not in json.dumps(facts)
            return httpx.Response(200,json={'message':{'content':json.dumps(output)}})
        transport=httpx.MockTransport(handler)
    client=TestClient(create_app('sqlite://',clock=lambda:NOW,ai_transport=transport))
    client.post('/api/demo');return client

def test_plan_joins_payment_and_shipment_evidence_without_mutation(monkeypatch):
    with setup(monkeypatch) as c:
        before=c.get('/api/findings').json()
        plan=c.post('/api/investigate/DEMO-005').json()
        assert {'payment-reconcile','carrier-reconcile'}<=set(s['id'] for s in plan['steps'])
        assert all(set(s['evidence_ids'])<=set(e['id'] for e in plan['evidence']) for s in plan['steps'])
        assert plan['source']=='verified_playbook' and len(plan['snapshot_sha256'])==64
        assert c.get('/api/findings').json()==before
        assert c.post('/api/investigate/NOT-AN-ORDER').status_code==404
        assert c.post('/api/investigate/DEMO-005').json()['snapshot_sha256']==plan['snapshot_sha256']

@pytest.mark.parametrize('output',[
 {'step_ids':['refund-now','carrier-reconcile']},
 {'step_ids':['payment-reconcile']},
 {'step_ids':['payment-reconcile','payment-reconcile']},
 {'step_ids':[None,'carrier-reconcile']},
 {'step_ids':['payment-reconcile','carrier-reconcile'],'cause':'Money stolen'},
 {'step_ids':'payment-reconcile'},None,[],
])
def test_rejects_invented_actions_missing_steps_and_model_facts(monkeypatch,output):
    # None needs an explicitly malformed JSON transport, rather than no model.
    with setup(monkeypatch,output if output is not None else []) as c:
        before=c.get('/api/findings').json()
        plan=c.post('/api/investigate/DEMO-005').json()
        assert plan['source']=='verified_playbook' and plan['model_status']=='rejected_or_unavailable'
        assert 'refund-now' not in json.dumps(plan) and 'Money stolen' not in json.dumps(plan)
        assert c.get('/api/findings').json()==before

def test_valid_ranking_can_change_order_but_not_step_content(monkeypatch):
    with setup(monkeypatch) as c:baseline=c.post('/api/investigate/DEMO-005').json()
    ids=[s['id'] for s in baseline['steps']][::-1]
    with setup(monkeypatch,{'step_ids':ids}) as c:
        plan=c.post('/api/investigate/DEMO-005').json()
        assert plan['source']=='local_ai_ranking'
        assert plan['steps']==baseline['steps'][::-1]
        assert plan['evidence']==baseline['evidence']
        assert plan['snapshot_sha256']==baseline['snapshot_sha256']

def test_snapshot_changes_when_policy_changes(monkeypatch):
    with setup(monkeypatch) as c:
        before=c.post('/api/investigate/DEMO-005').json()
        c.put('/api/policy',json={'paid_unfulfilled_hours':72,'pending_payment_hours':36})
        assert c.post('/api/investigate/DEMO-005').json()['snapshot_sha256']!=before['snapshot_sha256']

def test_protected_investigation_requires_operator_key():
    with TestClient(create_app('sqlite://',operator_key='x'*32)) as c:
        assert c.post('/api/investigate/DEMO-005').status_code==401
