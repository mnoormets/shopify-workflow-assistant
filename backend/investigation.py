"""Evidence-linked investigation plans; model output can reorder approved steps only."""
import hashlib,json
from .domain import RULE_VERSION

PLAYBOOKS={
 'PAYMENT_MISMATCH':('payment-reconcile','Compare the store and payment-provider transaction IDs, timestamps and settlement record.','Do not charge again based on a status mismatch.'),
 'SHIPMENT_MISMATCH':('carrier-reconcile','Compare carrier handover timestamps with the store fulfillment event and integration delivery log.','Do not mark fulfilled until the carrier event matches this order.'),
 'PAID_NOT_FULFILLED':('fulfillment-review','Check stock allocation and the fulfillment queue against the order age and configured threshold.','The delay alone does not identify its cause.'),
 'PAYMENT_PENDING':('pending-review','Check the provider transaction record and timestamps before a reminder or cancellation.','A pending store status is not proof of an unpaid transaction.'),
 'STOCK_SHORTAGE':('stock-review','Verify stock allocation and replenishment records before proposing a resolution.','No refund or replenishment is performed by this plan.'),
 'TRACKING_MISSING':('tracking-review','Check the carrier handover record and tracking synchronization log.','Missing tracking does not prove that the parcel was not shipped.'),
 'REFUNDED_FULFILLED':('return-review','Compare refund timestamps, return records and shipment evidence.','This can be a legitimate return; do not assume a payment error.'),
}

def build_plan(order_id,findings,generated_at,policy):
    found=sorted((f for f in findings if f.order_id==order_id),key=lambda f:({'high':0,'medium':1,'low':2}[f.severity],f.code))
    sources=[{'id':f.code,'severity':f.severity,'observation':f.reason,'facts':f.evidence} for f in found]
    steps=[]
    for f in found:
        step,text,caution=PLAYBOOKS[f.code]
        steps.append({'id':step,'check':text,'caution':caution,'evidence_ids':[f.code],'completion':'Record the compared source IDs, event times and observed outcome in the incident note.'})
    payload={'order_id':order_id,'rule_version':RULE_VERSION,'policy':policy.model_dump(),'evidence':sources,'steps':steps}
    digest=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return {**payload,'snapshot_sha256':digest,'generated_at':generated_at.isoformat(),'source':'verified_playbook','model_status':'not_configured','unknowns':['Root cause is not established by status fields alone.','Independent source records and integration logs must be checked by the operator.'],'notice':'Read-only investigation plan. No payment, shipment or store changes are executed.'}

def apply_ranking(plan,output):
    """Fail closed: no model-authored facts, causes, actions or extra fields accepted."""
    if not isinstance(output,dict) or set(output)!={'step_ids'}:raise ValueError('Only step_ids are accepted')
    ids=output['step_ids'];expected=[step['id'] for step in plan['steps']]
    if not isinstance(ids,list) or any(type(x) is not str for x in ids) or len(ids)!=len(expected) or len(set(ids))!=len(ids) or set(ids)!=set(expected):raise ValueError('Ranking must contain every approved step exactly once')
    by_id={s['id']:s for s in plan['steps']}
    return {**plan,'steps':[by_id[x] for x in ids],'source':'local_ai_ranking','model_status':'validated'}
