"""Local read-only review application. No merchant API credentials or actions."""
import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, String, JSON, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session
from sqlalchemy.pool import StaticPool
from sqlalchemy.exc import IntegrityError
from .domain import Order, ImportBatch, ReviewPolicy, evaluate, RULE_VERSION

ROOT = Path(__file__).resolve().parents[1]
log = logging.getLogger("shopify_ops")
class Base(DeclarativeBase): pass
class StoredOrder(Base):
    __tablename__ = "orders"
    order_id: Mapped[str] = mapped_column(String(60), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)
class ImportRun(Base):
    __tablename__ = "import_runs"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    digest: Mapped[str] = mapped_column(String(64))
    count: Mapped[str] = mapped_column(String(10))

class StoredPolicy(Base):
    __tablename__ = "review_policy"
    policy_id: Mapped[str] = mapped_column(String(10), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)

def create_app(database_url=None, clock=None, ai_transport=None):
    # Read only explicitly configured process settings; never load a .env file.
    default = f"sqlite:///{ROOT / 'data' / 'orders.db'}"
    (ROOT / "data").mkdir(exist_ok=True)
    url = database_url or os.environ.get("SHOPIFY_OPS_DATABASE_URL", default)
    kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}
    if url == "sqlite://": kwargs["poolclass"] = StaticPool
    engine = create_engine(url, **kwargs)
    Base.metadata.create_all(engine)
    clock = clock or (lambda: datetime.now(timezone.utc))
    @asynccontextmanager
    async def lifespan(app):
        yield
        engine.dispose()
    app = FastAPI(title="Shopify Workflow Review", version="0.1.0", lifespan=lifespan)
    app.state.engine = engine

    @app.get("/api/health")
    def health():
        return {"status":"ok", "rule_version":RULE_VERSION, "ai_enabled":bool(os.environ.get("SHOPIFY_OPS_MODEL")), "mode":"synthetic_demo"}

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
