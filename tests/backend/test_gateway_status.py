"""M6's narrow version-conditional status seam against actual PostgreSQL."""
from uuid import uuid4

from backend.registry.servers import Registry


def test_status_compare_and_set_preserves_edit_and_disabled(db):
    server_id = uuid4()
    with db.transaction() as c:
        c.execute("INSERT INTO servers(id,name,slug,url,enabled,status,auth_type) VALUES(%s,'fixture','status-fixture','https://example.test/mcp',true,'Unreachable','none')", (server_id,))
    registry = Registry(db, None, [])
    assert registry.set_server_status(server_id, 'Connected') is True
    assert registry.set_server_status(server_id, 'Unreachable', 'TIMEOUT', expected_version=1) is True
    with db.transaction() as c:
        c.execute("UPDATE servers SET version=2,status='Unreachable',status_reason='NOT_CHECKED' WHERE id=%s", (server_id,))
    assert registry.set_server_status(server_id, 'Connected', expected_version=1) is False
    assert registry.get_server(server_id)['status_reason'] == 'NOT_CHECKED'
    with db.transaction() as c:
        c.execute('UPDATE servers SET enabled=false WHERE id=%s', (server_id,))
    assert registry.set_server_status(server_id, 'Connected', expected_version=2) is True
    assert registry.get_server(server_id)['status'] == 'Disabled'
    assert registry.set_server_status(uuid4(), 'Connected', expected_version=1) is False
