import json
from app import app


def test_flow():
    client = app.test_client()

    # no pin -> unauthorized
    r = client.get('/api/state')
    assert r.status_code == 401

    # set pin via cookie (Werkzeug 3.x signature: key, value)
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
    r = client.post(
        f'/api/databases/{db_id}/tables/{t_id}/columns',
        json={'name': 'id', 'datatype': 'INT', 'is_primary': True, 'is_nullable': False}
    )
    assert r.status_code == 200
    c_id = r.json['column']['id']

    # link column to table (self link just for test)
    r = client.post(
        f'/api/databases/{db_id}/links',
        json={'from_type': 'column', 'from_id': c_id, 'to_type': 'table', 'to_id': t_id, 'note': 'fk-like'}
    )
    assert r.status_code == 200
    l_id = r.json['link']['id']

    # delete column
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


def test_duplicate_and_foreign_ref():
    client = app.test_client()
    client.set_cookie('vibe_pin', 'pin2')

    # create db
    r = client.post('/api/databases', json={'name': 'DB1'})
    assert r.status_code == 200
    db_id = r.json['database']['id']

    # add tables
    r = client.post(f'/api/databases/{db_id}/tables', json={'name': 'Users'})
    t_users = r.json['table']['id']
    r = client.post(f'/api/databases/{db_id}/tables', json={'name': 'Posts'})
    t_posts = r.json['table']['id']

    # add PK on Users
    r = client.post(f'/api/databases/{db_id}/tables/{t_users}/columns', json={'name': 'id', 'datatype': 'INT', 'is_primary': True, 'is_nullable': False})
    c_users_id = r.json['column']['id']

    # add FK on Posts referencing Users.id
    r = client.post(f'/api/databases/{db_id}/tables/{t_posts}/columns', json={'name': 'user_id', 'datatype': 'INT', 'is_primary': False, 'is_nullable': False, 'foreign_ref': {'table_id': t_users, 'column_id': c_users_id}})
    assert r.status_code == 200

    # duplicate db
    r = client.post(f'/api/databases/{db_id}/duplicate')
    assert r.status_code == 200
    new_db_id = r.json['database']['id']
    assert new_db_id != db_id

    # check that ref remapped
    r = client.get('/api/state')
    state = r.json
    copied = state[new_db_id]
    # find tables by name
    def find_by_name(obj, name):
        for tid, t in obj.items():
            if t['name'] == name:
                return tid, t
        return None, None
    users_tid, users_tbl = find_by_name(copied['tables'], 'Users')
    posts_tid, posts_tbl = find_by_name(copied['tables'], 'Posts')
    assert users_tid and posts_tid
    # find user_id column
    user_id_col = None
    for cid, c in posts_tbl['columns'].items():
        if c['name'] == 'user_id': user_id_col = c
    assert user_id_col and user_id_col['foreign_ref']
    assert user_id_col['foreign_ref']['table_id'] == users_tid
