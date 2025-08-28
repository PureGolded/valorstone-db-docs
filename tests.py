import json
from app import app, save_state


def test_flow():
    client = app.test_client()

    # no pin -> unauthorized
    r = client.get('/api/state')
    assert r.status_code == 401

    # set pin via cookie
    client.set_cookie('vibe_pin', 'testpin')

    # initial state empty
    r = client.get('/api/state')
    assert r.status_code == 200
    assert r.json == {}

    # create db
    r = client.post('/api/databases', json={'name': 'MyDB'})
    assert r.status_code == 200
    db_id = r.json['database']['id']

    # add table
    r = client.post(f'/api/databases/{db_id}/tables', json={'name': 'Users'})
    assert r.status_code == 200
    t_id = r.json['table']['id']

    # add column
    r = client.post(f'/api/databases/{db_id}/tables/{t_id}/columns', json={'name': 'id', 'datatype': 'INT', 'is_primary': True, 'is_nullable': False})
    assert r.status_code == 200
    c_id = r.json['column']['id']

    # link column to table (self link just for test)
    r = client.post(f'/api/databases/{db_id}/links', json={'from_type':'column','from_id': c_id, 'to_type':'table','to_id': t_id, 'note':'fk-like'})
    assert r.status_code == 200
    l_id = r.json['link']['id']

    # delete column -> link should be cleaned when deleting table later
    r = client.delete(f'/api/databases/{db_id}/tables/{t_id}/columns/{c_id}')
    assert r.status_code == 200

    # delete table
    r = client.delete(f'/api/databases/{db_id}/tables/{t_id}')
    assert r.status_code == 200

    # delete db
    r = client.delete(f'/api/databases/{db_id}')
    assert r.status_code == 200

    # state should be empty again
    r = client.get('/api/state')
    assert r.json == {}
