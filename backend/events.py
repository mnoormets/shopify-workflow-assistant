"""Authenticated durable webhook inbox, single-store order projection and audit trail.

Raw Shopify request bodies are authenticated, normalized and discarded. Only
review-relevant allow-listed fields persist; no customer/contact/address payload.
"""
import base64
import binascii
import hashlib
import hmac
import json
import os
import re
from datetime import datetime, timedelta, timezone
from uuid import UUID
from fastapi import HTTPException, Request, Query
from starlette.concurrency import run_in_threadpool
from sqlalchemy import String, JSON, select, func, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column, Session
from .db import Base, StoredOrder
from .domain import Order

MAX_BYTES=262144
TOPICS={'orders/create','orders/updated','orders/paid'}
DEMO_SHOP='workflow-demo.myshopify.com'
DEMO_SECRET='synthetic-local-simulation-not-a-real-app-secret'

class InboxEvent(Base):
    __tablename__='webhook_inbox'
    event_id:Mapped[str]=mapped_column(String(36),primary_key=True)
    shop:Mapped[str]=mapped_column(String(100))
    topic:Mapped[str]=mapped_column(String(40))
    body_digest:Mapped[str]=mapped_column(String(64))
    received_at:Mapped[str]=mapped_column(String(40))
    source_updated_at:Mapped[str]=mapped_column(String(40),default='')
    order_id:Mapped[str]=mapped_column(String(60),default='')
    payload:Mapped[dict]=mapped_column(JSON,default=dict)
    status:Mapped[str]=mapped_column(String(20),default='pending')
    attempts:Mapped[str]=mapped_column(String(10),default='0')
    error:Mapped[str]=mapped_column(String(100),default='')

class OrderProjection(Base):
    __tablename__='shopify_order_projection'
    order_id:Mapped[str]=mapped_column(String(60),primary_key=True)
    source_updated_at:Mapped[str]=mapped_column(String(40))
    payload:Mapped[dict]=mapped_column(JSON)

class EventAudit(Base):
    __tablename__='webhook_audit'
    event_id:Mapped[str]=mapped_column(String(36),primary_key=True)
    order_id:Mapped[str]=mapped_column(String(60))
    processed_at:Mapped[str]=mapped_column(String(40))
    outcome:Mapped[str]=mapped_column(String(20))
    before:Mapped[dict]=mapped_column(JSON)
    after:Mapped[dict]=mapped_column(JSON)


def timestamp(value):
    if not isinstance(value,str):raise ValueError('Timestamp required')
    result=datetime.fromisoformat(value.replace('Z','+00:00'))
    if result.tzinfo is None or result.utcoffset() is None:raise ValueError('UTC offset required')
    return result.astimezone(timezone.utc)


def normalize(raw,shop,now):
    if not isinstance(raw,dict):raise ValueError('Order object required')
    number=raw.get('id')
    if not isinstance(number,int) or isinstance(number,bool) or not 0<number<10**20:raise ValueError('Invalid order ID')
    created=timestamp(raw.get('created_at'));updated=timestamp(raw.get('updated_at'))
    if created>now or updated<created or updated>now+timedelta(minutes=5):raise ValueError('Invalid chronology')
    financial=raw.get('financial_status')
    financial='pending' if financial=='authorized' else financial
    if financial not in {'paid','pending','refunded','voided'}:raise ValueError('Unsupported financial state')
    fulfillment=raw.get('fulfillment_status') or 'unfulfilled'
    items=raw.get('line_items',[])
    if not isinstance(items,list) or any(not isinstance(i,dict) for i in items):raise ValueError('Invalid items')
    if any('requires_shipping' in i and not isinstance(i['requires_shipping'],bool) for i in items):raise ValueError('Invalid shipping flag')
    physical=not items or any(i.get('requires_shipping',True) for i in items)
    fulfillment_rows=raw.get('fulfillments',[])
    if not isinstance(fulfillment_rows,list) or any(not isinstance(f,dict) for f in fulfillment_rows):raise ValueError('Invalid fulfillments')
    # This adapter has no independent carrier evidence. Never infer handover from
    # Shopify's fulfillment status; multiple fulfillment tracking remains a limitation.
    tracking=next((f.get('tracking_number') for f in fulfillment_rows if f.get('tracking_number')), '')
    order=Order.model_validate({'order_id':f'S-{hashlib.sha256(shop.encode()).hexdigest()[:10]}-{number}',
        'created_at':created,'financial_status':financial,'fulfillment_status':fulfillment,
        'total':raw.get('total_price'),'currency':raw.get('currency'),
        'physical_goods':physical,'delivery_method':'tracked' if physical else 'digital','tracking_number':tracking})
    return order.model_dump(mode='json'),updated.isoformat()


def verify_signature(body,signature,secret):
    try:
        supplied=base64.b64decode(signature,validate=True)
    except (ValueError,binascii.Error,TypeError):raise HTTPException(401,'Invalid webhook signature')
    expected=hmac.new(secret.encode(),body,hashlib.sha256).digest()
    if not hmac.compare_digest(supplied,expected):raise HTTPException(401,'Invalid webhook signature')


def accept_event(engine,body,headers,secret,allowed_shop,now):
    verify_signature(body,headers.get('x-shopify-hmac-sha256',''),secret)
    shop=headers.get('x-shopify-shop-domain','').lower()
    if shop!=allowed_shop or not re.fullmatch(r'[a-z0-9][a-z0-9-]*\.myshopify\.com',shop):raise HTTPException(403,'Shop is not configured')
    topic=headers.get('x-shopify-topic','')
    if topic not in TOPICS:raise HTTPException(400,'Unsupported webhook topic')
    try:event_id=str(UUID(headers.get('x-shopify-webhook-id','')))
    except (ValueError,TypeError,AttributeError):raise HTTPException(400,'Invalid webhook ID')
    digest=hashlib.sha256(body).hexdigest()
    payload={};updated='';error='';status='pending'
    try:payload,updated=normalize(json.loads(body),shop,now)
    except (ValueError,TypeError,KeyError):
        # No exception text, raw payload or customer details enter persistence/logs.
        error='invalid_or_unsupported_order_payload';status='failed'
    def receipt(previous):
        if previous.body_digest!=digest or previous.shop!=shop or previous.topic!=topic:raise HTTPException(409,'Webhook ID reused with different content')
        return {'event_id':event_id,'status':previous.status,'replayed':True}
    try:
        with Session(engine) as session,session.begin():
            previous=session.get(InboxEvent,event_id)
            if previous:return receipt(previous)
            session.add(InboxEvent(event_id=event_id,shop=shop,topic=topic,body_digest=digest,
                received_at=now.isoformat(),source_updated_at=updated,order_id=payload.get('order_id',''),
                payload=payload,status=status,error=error,attempts='0'))
        return {'event_id':event_id,'status':status,'replayed':False}
    except IntegrityError:
        with Session(engine) as session:
            previous=session.get(InboxEvent,event_id)
            if previous:return receipt(previous)
        raise HTTPException(409,'Concurrent ingestion; retry delivery')


def process_events(engine,now,limit=100):
    outcomes=[]
    with Session(engine) as session,session.begin():
        # SQLite serializes writers; PostgreSQL locks only claimed pending rows.
        if engine.dialect.name=='sqlite':session.connection().exec_driver_sql('BEGIN IMMEDIATE')
        statement=select(InboxEvent).where(InboxEvent.status=='pending').order_by(InboxEvent.received_at,InboxEvent.event_id).limit(limit)
        if engine.dialect.name=='postgresql':statement=statement.with_for_update(skip_locked=True)
        claimed=list(session.scalars(statement))
        if engine.dialect.name=='postgresql':
            # Serialize all projections touched by this batch in a consistent order.
            # Row locks alone do not protect projections that do not yet exist.
            for order_id in sorted({e.order_id for e in claimed}):
                lock_key=int.from_bytes(hashlib.sha256(order_id.encode()).digest()[:8], 'big', signed=True)
                session.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key':lock_key})
        for event in claimed:
            event.attempts=str(int(event.attempts)+1)
            projection=session.get(OrderProjection,event.order_id)
            before=projection.payload.copy() if projection else {}
            status='processed'
            if projection:
                prior=timestamp(projection.source_updated_at);incoming=timestamp(event.source_updated_at)
                if incoming<prior:status='stale'
                elif incoming==prior:status='unchanged' if projection.payload==event.payload else 'conflict'
            if status=='processed':
                session.merge(OrderProjection(order_id=event.order_id,source_updated_at=event.source_updated_at,payload=event.payload))
                existing=session.get(StoredOrder,event.order_id)
                payload=event.payload.copy()
                # External provider/carrier/stock observations must survive store updates.
                if existing:
                    for field in ('provider_status','shipment_status','stock_status'):payload[field]=existing.payload.get(field,'unknown')
                session.merge(StoredOrder(order_id=event.order_id,payload=payload))
                session.flush() # Make a new projection visible to later events in this batch.
            event.status=status
            if status=='conflict':event.error='same_timestamp_conflicting_snapshot'
            after=event.payload if status=='processed' else before
            session.add(EventAudit(event_id=event.event_id,order_id=event.order_id,processed_at=now.isoformat(),
                outcome=status,before=before,after=after))
            outcomes.append({'event_id':event.event_id,'order_id':event.order_id,'outcome':status})
    return outcomes


def install_event_routes(app,engine,clock,webhook_secret=None,allowed_shop=None):
    secret=webhook_secret or os.environ.get('SHOPIFY_OPS_WEBHOOK_SECRET')
    shop=(allowed_shop or os.environ.get('SHOPIFY_OPS_SHOP','')).lower()
    configured=bool(secret and shop)

    @app.post('/api/webhooks/shopify')
    async def webhook(request:Request):
        if not configured:raise HTTPException(503,'Shopify webhook receiver is not configured')
        body=bytearray()
        async for chunk in request.stream():
            if len(body)+len(chunk)>MAX_BYTES:raise HTTPException(413,'Webhook body exceeds 256 KiB')
            body.extend(chunk)
        return await run_in_threadpool(accept_event,engine,bytes(body),request.headers,secret,shop,clock())

    @app.post('/api/events/process')
    def process():return {'outcomes':process_events(engine,clock())}

    @app.get('/api/events')
    def events(order_id:str=Query(default='',max_length=60)):
        with Session(engine) as session:
            query=select(InboxEvent).order_by(InboxEvent.received_at.desc(),InboxEvent.event_id.desc()).limit(100)
            if order_id:query=query.where(InboxEvent.order_id==order_id)
            rows=session.scalars(query).all()
            counts=dict(session.execute(select(InboxEvent.status,func.count()).group_by(InboxEvent.status)).all())
            return {'receiver_configured':configured,'counts':counts,'events':[
                {'event_id':e.event_id,'order_id':e.order_id,'topic':e.topic,'source_updated_at':e.source_updated_at,
                'status':e.status,'attempts':int(e.attempts),'error':e.error} for e in rows]}

    @app.get('/api/events/{event_id}/audit')
    def audit(event_id:str):
        with Session(engine) as session:
            entry=session.get(EventAudit,event_id)
            if not entry:raise HTTPException(404,'Processed event audit not found')
            return {'event_id':entry.event_id,'order_id':entry.order_id,'outcome':entry.outcome,
                'processed_at':entry.processed_at,'before':entry.before,'after':entry.after}

    @app.post('/api/integration-demo')
    def integration_demo():
        if configured:raise HTTPException(403,'Simulator is disabled with a configured real receiver')
        now=clock()
        with Session(engine) as session:
            first=session.get(InboxEvent,'10000000-0000-0000-0000-000000000001')
            anchor=timestamp(first.received_at) if first else now
        base={'id':998877,'created_at':(anchor-timedelta(hours=72)).isoformat(),
            'updated_at':(anchor-timedelta(hours=3)).isoformat(),'financial_status':'pending',
            'fulfillment_status':None,'total_price':'49.90','currency':'EUR','line_items':[{'requires_shipping':True}],
            'customer':{'email':'synthetic-not-stored@example.invalid'}}
        cases=[('10000000-0000-0000-0000-000000000001',base),
            ('10000000-0000-0000-0000-000000000002',{**base,'financial_status':'paid','updated_at':(anchor-timedelta(hours=2)).isoformat()}),
            ('10000000-0000-0000-0000-000000000003',{**base,'updated_at':(anchor-timedelta(hours=4)).isoformat()})]
        receipts=[]
        for event_id,payload in [*cases,cases[1]]:
            body=json.dumps(payload).encode();signature=base64.b64encode(hmac.new(DEMO_SECRET.encode(),body,hashlib.sha256).digest()).decode()
            receipts.append(accept_event(engine,body,{'x-shopify-hmac-sha256':signature,'x-shopify-webhook-id':event_id,
                'x-shopify-shop-domain':DEMO_SHOP,'x-shopify-topic':'orders/updated'},DEMO_SECRET,DEMO_SHOP,now))
        return {'receipts':receipts,'outcomes':process_events(engine,now),'note':'Synthetic local simulation; not a live Shopify integration.'}
