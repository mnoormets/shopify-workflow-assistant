"""Durable inbox worker. Run separately; ingestion does not depend on this process."""
import argparse
import json
import time
from datetime import datetime,timezone
from sqlalchemy.exc import SQLAlchemyError
from .api import app
from .events import process_events

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--once',action='store_true')
    parser.add_argument('--interval',type=float,default=2);parser.add_argument('--limit',type=int,default=100)
    args=parser.parse_args()
    if not 0.5<=args.interval<=60 or not 1<=args.limit<=1000:parser.error('interval 0.5-60 seconds; limit 1-1000')
    try:
        while True:
            try:
                outcomes=process_events(app.state.engine,datetime.now(timezone.utc),args.limit)
                if outcomes:print(json.dumps({'outcomes':outcomes}),flush=True)
            except SQLAlchemyError:
                # The transaction rolled back. Never print exception parameters/payloads.
                print(json.dumps({'error':'database_transaction_failed','action':'pending events retained for retry'}),flush=True)
                if args.once:raise SystemExit(1)
            if args.once:return
            time.sleep(args.interval)
    except KeyboardInterrupt:return
if __name__=='__main__':main()
