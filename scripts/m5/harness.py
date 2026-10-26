"""Isolated M5 composition only; not the final gateway application."""
import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager, suppress

import psycopg
import uvicorn
from fastapi import FastAPI
from starlette.concurrency import run_in_threadpool

from backend.api import BrowserConfig,create_api
from backend.audit.records import Audit
from backend.db.database import Database
from backend.identity.auth import Identity
from backend.identity.api_keys import ApiKeys
from backend.identity.members import Members
from backend.registry.servers import Registry
from backend.registry.secret_store import SecretStore
from backend.errors import PlatformError


def database_available(db):
    with db.connect() as connection:
        connection.execute('SELECT 1')


async def monitor_owner(db, restart=os._exit, interval=2):
    """Stay fenced during an outage; restart only after the database returns."""
    while True:
        await asyncio.sleep(interval)
        try:
            await run_in_threadpool(db.check_owner)
        except PlatformError:
            break
    while True:
        try:
            await run_in_threadpool(database_available, db)
        except psycopg.Error:
            await asyncio.sleep(interval)
            continue
        logging.warning('Database ownership was lost; restarting for exclusive recovery.')
        restart(75)
        return


def components():
    db=Database(psycopg.conninfo.make_conninfo(host=os.environ['PGHOST'],port=os.getenv('PGPORT','5432'),
        user=os.environ['PGUSER'],dbname=os.environ['PGDATABASE'],password=os.environ['PGPASSWORD']))
    db.migrate(); db.acquire_owner()
    identity=Identity(db)
    with db.transaction() as c:
        owner=c.execute('SELECT id FROM installation').fetchone()['id']
    secrets=SecretStore(os.environ['M5_SECRET_NAMESPACE'],owner)
    registry=Registry(db,secrets,json.loads(os.getenv('M5_INTERNAL_URLS','[]')))
    audit=Audit(db,identity)
    audit.recover(); registry.recover()
    config=BrowserConfig(os.environ['M5_ORIGIN'],os.getenv('M5_LOCAL_HTTP','false').lower()=='true',os.getenv('M5_LISTEN_HOST','127.0.0.1'))
    return db,identity,Members(db,config.origin),ApiKeys(db,identity),registry,audit,config


@asynccontextmanager
async def lifespan(app):
    values=components()
    app.mount('/',create_api(*values))
    supervisor=asyncio.create_task(monitor_owner(values[0]))
    try:
        yield
    finally:
        supervisor.cancel()
        with suppress(asyncio.CancelledError):
            await supervisor
        values[4].secrets.close(); values[0].close()


app=FastAPI(lifespan=lifespan,docs_url=None,openapi_url=None)

if __name__=='__main__':
    uvicorn.run(app,host=os.getenv('M5_LISTEN_HOST','127.0.0.1'),port=8000,
                access_log=False,log_level='warning',workers=1)
