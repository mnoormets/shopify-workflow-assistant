"""Synthetic evidence coverage evaluation; no merchant accuracy claim."""
import json,os
from datetime import datetime,timezone
from pathlib import Path
from fastapi.testclient import TestClient
from .api import create_app

def main():
    previous=os.environ.pop('SHOPIFY_OPS_MODEL',None)
    try:
        with TestClient(create_app('sqlite://',clock=lambda:datetime(2026,10,9,tzinfo=timezone.utc))) as c:
            c.post('/api/scenario');findings=c.get('/api/findings').json()['findings']
            steps=active=0;errors=[]
            for i in range(120):
                order_id=f'SCENARIO-{i:04}';plan=c.post('/api/investigate/'+order_id).json()
                active+=bool(plan['steps']);steps+=len(plan['steps'])
                if bool(plan['steps'])!=(i%8 in (0,1,2,3,4)):errors.append(order_id+': wrong exception group')
                actual={f['code'] for f in findings if f['order_id']==order_id}
                if {e['id'] for e in plan['evidence']}!=actual:errors.append(order_id+': evidence mismatch')
                if any(not set(s['evidence_ids'])<=actual for s in plan['steps']):errors.append(order_id+': unsupported citation')
            report={'scope':'120 authored synthetic orders; no real-model or merchant accuracy claim','orders':120,'active_orders':active,'clean_orders':120-active,'cited_steps':steps,'coverage_errors':errors,'passed':not errors,'model_execution':'disabled; adversarial model-output contract tested separately in pytest'}
            Path('investigation-evaluation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
            if errors:raise SystemExit(1)
    finally:
        if previous is not None:os.environ['SHOPIFY_OPS_MODEL']=previous
if __name__=='__main__':main()
