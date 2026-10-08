"""Non-destructive local schema upgrades; production deploys need migration orchestration."""
import json
from sqlalchemy import inspect,text
from .db import Base

def initialize(engine):
    Base.metadata.create_all(engine)
    columns={c['name'] for c in inspect(engine).get_columns('incident_audit')}
    if 'revision' not in columns:
        with engine.begin() as connection:
            connection.execute(text('ALTER TABLE incident_audit ADD COLUMN revision INTEGER NOT NULL DEFAULT 0'))
            rows=connection.execute(text('SELECT audit_id, incident_id, timestamp, after FROM incident_audit ORDER BY timestamp, audit_id')).mappings().all()
            sequence={}
            for row in rows:
                sequence[row['incident_id']]=sequence.get(row['incident_id'],0)+1
                after=row['after'] if isinstance(row['after'],dict) else json.loads(row['after'])
                revision=after.get('revision',sequence[row['incident_id']])
                connection.execute(text('UPDATE incident_audit SET revision=:revision WHERE audit_id=:audit_id'),{'revision':revision,'audit_id':row['audit_id']})
