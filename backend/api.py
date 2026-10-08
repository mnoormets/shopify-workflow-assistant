"""Local read-only review application. No merchant API credentials or actions."""
import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, String, JSON, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from sqlalchemy.exc import IntegrityError
from .domain import Order, ImportBatch, ReviewPolicy, evaluate, RULE_VERSION
from .db import Base, StoredOrder, ImportRun, StoredPolicy
from .events import install_event_routes
from .incidents import install as install_incidents
from .migrations import initialize

ROOT = Path(__file__).resolve().parents[1]
log = logging.getLogger("shopify_ops")
def create_app(database_url=None, clock=None, ai_transport=None, webhook_secret=None, allowed_shop=None, operator_key=None):
    # Read only explicitly configured process settings; never load a .env file.
    configured_key = operator_key if operator_key is not None else os.environ.get("SHOPIFY_OPS_OPERATOR_KEY")
    if configured_key is not None and (not isinstance(configured_key, str) or len(configured_key) < 32 or configured_key.strip() != configured_key):
        raise ValueError("Operator key must contain at least 32 characters and no surrounding whitespace")
    default = f"sqlite:///{ROOT / 'data' / 'orders.db'}"
    (ROOT / "data").mkdir(exist_ok=True)
    url = database_url or os.environ.get("SHOPIFY_OPS_DATABASE_URL", default)
    kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}
    if url == "sqlite://": kwargs["poolclass"] = StaticPool
    engine = create_engine(url, **kwargs)
    initialize(engine)
    clock = clock or (lambda: datetime.now(timezone.utc))
    @asynccontextmanager
    async def lifespan(app):
        yield
        engine.dispose()
    app = FastAPI(title="Shopify Workflow Review", version="0.4.0", lifespan=lifespan)
    app.state.engine = engine
    # A shared key identifies this installation's operator, not an individual user.
    app.state.operator_identity = "local-operator" if configured_key else None

    @app.middleware("http")
    async def operator_access(request, call_next):
        public = request.url.path in {"/api/health", "/api/webhooks/shopify"}
        if configured_key and request.url.path.startswith("/api/") and not public:
            supplied = request.headers.get("X-Operator-Key", "")
            if not hmac.compare_digest(supplied.encode("utf-8"), configured_key.encode("utf-8")):
                return JSONResponse({"detail": "Operaatori ligipääsuvõti puudub või on vale."}, status_code=401, headers={"Cache-Control": "no-store"})
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    install_event_routes(app, engine, clock, webhook_secret, allowed_shop)

    @app.get("/api/health")
    def health():
        return {"status":"ok", "rule_version":RULE_VERSION, "ai_enabled":bool(os.environ.get("SHOPIFY_OPS_MODEL")), "mode":"protected_local_review" if configured_key else "synthetic_demo", "operator_auth":bool(configured_key)}

    def read_policy(session):
        stored = session.get(StoredPolicy, "default")
        return ReviewPolicy.model_validate(stored.payload) if stored else ReviewPolicy()

    @app.get("/api/policy")
    def get_policy():
        with Session(engine) as session:
            return read_policy(session).model_dump()

    @app.put("/api/policy")
    def set_policy(policy: ReviewPolicy):
        try:
            with Session(engine) as session, session.begin():
                session.merge(StoredPolicy(policy_id="default", payload=policy.model_dump()))
        except IntegrityError as exc:
            raise HTTPException(409, "Concurrent settings update; retry") from exc
        return policy.model_dump()

    def import_orders(batch: ImportBatch, key: str):
        if not key or len(key)>100: raise HTTPException(422, "Invalid Idempotency-Key")
        now=clock()
        try:
            for order in batch.orders: evaluate(order, now)
        except ValueError as exc: raise HTTPException(422,str(exc)) from exc
        payload=[o.model_dump(mode="json") for o in sorted(batch.orders,key=lambda o:o.order_id)]
        digest=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
        try:
            with Session(engine) as session, session.begin():
                previous=session.get(ImportRun,key)
                if previous:
                    if previous.digest!=digest: raise HTTPException(409,"Key already used for a different batch")
                    return {"imported":int(previous.count),"replayed":True}
                for item in payload:
                    session.merge(StoredOrder(order_id=item["order_id"],payload=item))
                session.add(ImportRun(key=key,digest=digest,count=str(len(payload))))
            log.info("Import completed: %d orders",len(payload))
            return {"imported":len(payload),"replayed":False}
        except IntegrityError as exc:
            # Concurrent key reuse: the transaction is rolled back, never partly imported.
            raise HTTPException(409,"Concurrent import detected; retry the same key") from exc

    @app.post("/api/import")
    def ingest(batch: ImportBatch, idempotency_key: str=Header(min_length=1,max_length=100)):
        return import_orders(batch,idempotency_key)

    @app.post("/api/demo")
    def demo():
        return import_orders(ImportBatch.model_validate(json.loads((ROOT/"fixtures/demo.json").read_text())),"demo-v1")

    @app.post("/api/scenario")
    def scenario():
        from datetime import timedelta
        anchor=clock().replace(minute=0,second=0,microsecond=0)
        cases=[]
        for index in range(120):
            kind=index%8
            row={"order_id":f"SCENARIO-{index:04}","created_at":(anchor-timedelta(hours=2)).isoformat(),"financial_status":"paid","fulfillment_status":"fulfilled","total":f"{20+index}.00","currency":"EUR","tracking_number":f"SYNTHETIC-{index:04}"}
            if kind==0:row.update(created_at=(anchor-timedelta(hours=72)).isoformat(),fulfillment_status="unfulfilled",stock_status="insufficient")
            if kind==1:row.update(financial_status="pending",provider_status="paid",fulfillment_status="unfulfilled",shipment_status="handed_over")
            if kind==2:row.update(financial_status="refunded")
            if kind==3:row.update(tracking_number="")
            if kind==4:row.update(financial_status="pending",fulfillment_status="unfulfilled",created_at=(anchor-timedelta(hours=40)).isoformat())
            cases.append(row)
        result=import_orders(ImportBatch.model_validate({"orders":cases}),"scenario-"+anchor.strftime("%Y%m%d%H"))
        return {**result,"scenario":"120 authored synthetic orders; five exception groups and three clean groups","anchor":anchor.isoformat()}

    def all_findings():
        now=clock()
        with Session(engine) as session:
            policy=read_policy(session)
            rows=session.scalars(select(StoredOrder)).all()
            found=[f for row in rows for f in evaluate(Order.model_validate(row.payload),now,policy)]
            count=len(rows)
        priority={"high":0,"medium":1,"low":2}
        found.sort(key=lambda f:(priority[f.severity],f.order_id,f.code))
        return found,count,now,policy

    install_incidents(app,engine,clock,all_findings)

    @app.get("/api/findings")
    def findings(q: str=Query(default="",max_length=100), severity: str=Query(default="",pattern="^(high|medium|low|)$")):
        found,count,now,policy=all_findings()
        filtered=[f for f in found if (not severity or f.severity==severity) and (not q or q.lower() in f"{f.order_id} {f.code} {f.reason}".lower())]
        return {"orders_scanned":count,"total_findings":len(found),"generated_at":now.isoformat(),"rule_version":RULE_VERSION,"policy":policy.model_dump(),"findings":[f.model_dump() for f in filtered]}

    @app.post("/api/explain/{order_id}/{code}")
    async def explain(order_id: str, code: str):
        found,_,_,_=all_findings()
        finding=next((f for f in found if f.order_id==order_id and f.code==code),None)
        if not finding: raise HTTPException(404,"Finding not found")
        model=os.environ.get("SHOPIFY_OPS_MODEL")
        if not model:
            return {"source":"rules","explanation":finding.reason,"checks":[finding.suggested_action],"notice":"Rule-based explanation. Local AI is not configured."}
        facts={"code":finding.code,"reason":finding.reason,"suggested_action":finding.suggested_action,"evidence":finding.evidence}
        schema={"type":"object","properties":{"explanation":{"type":"string"},"checks":{"type":"array","items":{"type":"string"}}},"required":["explanation","checks"],"additionalProperties":False}
        try:
            async with httpx.AsyncClient(timeout=45,transport=ai_transport) as client:
                response=await client.post("http://127.0.0.1:11434/api/chat",json={"model":model,"stream":False,"format":schema,"options":{"temperature":0},"messages":[{"role":"system","content":"Explain these verified order-review facts briefly in Estonian. Use only supplied facts. Do not invent causes, customer details or completed actions. Give human checks, never commands to charge, refund or contact anyone. Return JSON with explanation and checks."},{"role":"user","content":json.dumps(facts)}]})
                response.raise_for_status()
                output=json.loads(response.json()["message"]["content"])
                if set(output)!={"explanation","checks"} or not isinstance(output["explanation"],str) or not isinstance(output["checks"],list) or not 1<=len(output["checks"])<=8 or any(not isinstance(c,str) or len(c)>1000 for c in output["checks"]) or len(output["explanation"])>2000:raise ValueError("Invalid explanation")
            return {"source":"local_ai",**output,"notice":"AI draft: verify against the evidence before using."}
        except (httpx.HTTPError,KeyError,ValueError,TypeError) as exc:
            log.warning("Local AI unavailable or invalid: %s",type(exc).__name__)
            return {"source":"rules_fallback","explanation":finding.reason,"checks":[finding.suggested_action],"notice":"Local AI unavailable; verified rule explanation shown."}

    dist=ROOT/"frontend/dist"
    if dist.exists():
        app.mount("/assets",StaticFiles(directory=dist/"assets"),name="assets")
        @app.get("/")
        def index(): return FileResponse(dist/"index.html")
    return app

app=create_app()
