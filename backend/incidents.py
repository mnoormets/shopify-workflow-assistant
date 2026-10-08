"""Persistent triage: compare-and-swap revisions and transactional audit history."""
import hashlib,json
from uuid import uuid4
from typing import Literal
from fastapi import HTTPException,Query
from pydantic import BaseModel,ConfigDict,Field,field_validator
from sqlalchemy import String,Integer,Boolean,JSON,select,update
from sqlalchemy.orm import Session,Mapped,mapped_column
from sqlalchemy.exc import IntegrityError
from .db import Base

class Incident(Base):
    __tablename__='review_incidents'
    incident_id:Mapped[str]=mapped_column(String(32),primary_key=True)
    order_id:Mapped[str]=mapped_column(String(60),index=True)
    code:Mapped[str]=mapped_column(String(60))
    status:Mapped[str]=mapped_column(String(20),default='open')
    revision:Mapped[int]=mapped_column(Integer,default=1)
    active:Mapped[bool]=mapped_column(Boolean,default=True)
    owner:Mapped[str]=mapped_column(String(80),default='')
    finding:Mapped[dict]=mapped_column(JSON)
    first_seen:Mapped[str]=mapped_column(String(40))
    last_seen:Mapped[str]=mapped_column(String(40))

class IncidentAudit(Base):
    __tablename__='incident_audit'
    audit_id:Mapped[str]=mapped_column(String(36),primary_key=True)
    incident_id:Mapped[str]=mapped_column(String(32),index=True)
    timestamp:Mapped[str]=mapped_column(String(40))
    revision:Mapped[int]=mapped_column(Integer)
    actor:Mapped[str]=mapped_column(String(80))
    action:Mapped[str]=mapped_column(String(40))
    note:Mapped[str]=mapped_column(String(1000),default='')
    before:Mapped[dict]=mapped_column(JSON)
    after:Mapped[dict]=mapped_column(JSON)

class Edit(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:int=Field(ge=1,strict=True)
    status:Literal['open','investigating','resolved','dismissed']
    owner:str=Field(default='',max_length=80)
    actor:str=Field(min_length=1,max_length=80)
    note:str=Field(min_length=1,max_length=1000)
    @field_validator('actor','note')
    @classmethod
    def nonblank(cls,value):
        if not value.strip():raise ValueError('Must not be blank')
        return value.strip()

TRANSITIONS={'open':{'investigating','dismissed'},'investigating':{'open','resolved','dismissed'},'resolved':{'investigating'},'dismissed':{'investigating'}}

def serialize(row):
    return {key:getattr(row,key) for key in ['incident_id','order_id','code','status','revision','active','owner','finding','first_seen','last_seen']}

def install(app,engine,clock,findings):
    def audit(session,row,action,actor,note,before):
        session.add(IncidentAudit(audit_id=str(uuid4()),incident_id=row.incident_id,timestamp=clock().isoformat(),revision=row.revision,actor=actor,action=action,note=note,before=before,after=serialize(row)))

    @app.post('/api/incidents/sync')
    def sync():
        found,_,now,_=findings();current={hashlib.sha256(f'{f.order_id}:{f.code}'.encode()).hexdigest()[:32]:f for f in found}
        created=changed=0
        try:
            with Session(engine) as session,session.begin():
                rows={r.incident_id:r for r in session.scalars(select(Incident)).all()}
                for key,finding in current.items():
                    row=rows.get(key);payload=finding.model_dump()
                    if row is None:
                        row=Incident(incident_id=key,order_id=finding.order_id,code=finding.code,status='open',revision=1,active=True,owner='',finding=payload,first_seen=now.isoformat(),last_seen=now.isoformat())
                        session.add(row);audit(session,row,'detected','system','',{});created+=1
                    elif row.finding!=payload or not row.active:
                        before=serialize(row);revision=row.revision
                        result=session.execute(update(Incident).where(Incident.incident_id==key,Incident.revision==revision).values(finding=payload,active=True,last_seen=now.isoformat(),revision=revision+1))
                        if result.rowcount!=1:raise HTTPException(409,'Concurrent incident change; retry sync')
                        session.refresh(row);audit(session,row,'observation_updated','system','',before);changed+=1
                for key,row in rows.items():
                    if key not in current and row.active:
                        before=serialize(row);revision=row.revision
                        result=session.execute(update(Incident).where(Incident.incident_id==key,Incident.revision==revision).values(active=False,last_seen=now.isoformat(),revision=revision+1))
                        if result.rowcount!=1:raise HTTPException(409,'Concurrent incident change; retry sync')
                        session.refresh(row);audit(session,row,'detection_cleared','system','',before);changed+=1
        except IntegrityError as exc:raise HTTPException(409,'Concurrent sync; retry') from exc
        return {'created':created,'changed':changed,'active_findings':len(current)}

    @app.get('/api/incidents')
    def listing(status:Literal['','open','investigating','resolved','dismissed']='',q:str=Query(default='',max_length=100),limit:int=Query(default=100,ge=1,le=200)):
        with Session(engine) as session:
            statement=select(Incident).order_by(Incident.first_seen.desc(),Incident.incident_id)
            if status:statement=statement.where(Incident.status==status)
            if q:
                # Literal case-insensitive substring: escape SQL wildcard characters.
                escaped=q.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
                statement=statement.where(Incident.order_id.ilike('%'+escaped+'%',escape='\\'))
            rows=session.scalars(statement.limit(limit+1)).all()
            return {'incidents':[serialize(r) for r in rows[:limit]],'has_more':len(rows)>limit}

    @app.get('/api/incidents/{incident_id}')
    def detail(incident_id:str):
        with Session(engine) as session:
            row=session.get(Incident,incident_id)
            if not row:raise HTTPException(404,'Incident not found')
            history=session.scalars(select(IncidentAudit).where(IncidentAudit.incident_id==incident_id).order_by(IncidentAudit.revision,IncidentAudit.audit_id)).all()
            return {'incident':serialize(row),'history':[{'id':r.audit_id,'timestamp':r.timestamp,'revision':r.revision,'actor':r.actor,'action':r.action,'note':r.note,'before':r.before,'after':r.after} for r in history]}

    @app.patch('/api/incidents/{incident_id}')
    def edit(incident_id:str,body:Edit):
        with Session(engine) as session,session.begin():
            row=session.get(Incident,incident_id)
            if not row:raise HTTPException(404,'Incident not found')
            if row.revision!=body.revision:raise HTTPException(409,'Incident changed; refresh before editing')
            if body.status!=row.status and body.status not in TRANSITIONS[row.status]:raise HTTPException(422,'Invalid transition; investigate before resolving')
            before=serialize(row)
            changed=session.execute(update(Incident).where(Incident.incident_id==incident_id,Incident.revision==body.revision).values(status=body.status,owner=body.owner.strip(),revision=body.revision+1))
            if changed.rowcount!=1:raise HTTPException(409,'Concurrent incident change; refresh')
            session.refresh(row);audit(session,row,'operator_update',app.state.operator_identity or body.actor,body.note,before)
            return serialize(row)
