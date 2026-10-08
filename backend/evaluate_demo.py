import json
from datetime import datetime,timezone
from pathlib import Path
from .domain import ImportBatch,evaluate

def main():
    root=Path(__file__).resolve().parents[1]
    batch=ImportBatch.model_validate(json.loads((root/"fixtures/demo.json").read_text()))
    expected={("DEMO-001","PAID_NOT_FULFILLED"),("DEMO-001","STOCK_SHORTAGE"),("DEMO-002","PAYMENT_PENDING"),("DEMO-003","REFUNDED_FULFILLED"),("DEMO-004","TRACKING_MISSING"),("DEMO-005","PAYMENT_PENDING"),("DEMO-005","PAYMENT_MISMATCH"),("DEMO-005","SHIPMENT_MISMATCH")}
    now=datetime(2026,10,8,10,tzinfo=timezone.utc)
    actual={(f.order_id,f.code) for o in batch.orders for f in evaluate(o,now)}
    report={"dataset":"8 synthetic demo orders; not real merchant data","true_positives":len(actual&expected),"false_positives":len(actual-expected),"false_negatives":len(expected-actual),"exact_fixture_match":actual==expected}
    print(json.dumps(report,indent=2))
    if actual!=expected:raise SystemExit(1)
if __name__=="__main__":main()
