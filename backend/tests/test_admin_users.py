import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import create_app
from app.api.auth import _hash_password
from app.extensions import db
from app.models import User


class Config:
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = JWT_SECRET_KEY = "test"
    JWT_EXPIRES_DELTA = __import__('datetime').timedelta(hours=1)
    FRONTEND_ORIGINS = ["http://localhost"]
    AUTO_CREATE_DB = True
    TASK_RECOVER_ON_STARTUP = False
    DEMO_ADMIN_USERNAME = "admin"
    DEMO_ADMIN_PASSWORD = "admin123"


class AdminUsersTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(Config)
        self.ctx = self.app.app_context(); self.ctx.push()
        db.create_all()
        hashed, _ = _hash_password("admin123")
        db.session.add(User(username="admin", password_hash=hashed, nickname="管理员", role="admin", status=1))
        db.session.commit()
        self.client = self.app.test_client()
        self.token = self.client.post('/api/auth/login', json={'username':'admin','password':'admin123'}).get_json()['data']['token']
        self.headers = {'Authorization': f'Bearer {self.token}'}

    def tearDown(self):
        db.session.remove(); db.drop_all(); self.ctx.pop()

    def test_admin_can_create_list_update_and_reset_user(self):
        created = self.client.post('/api/admin/users', headers=self.headers, json={'username':'zhangsan','password':'123456','nickname':'张三','role':'user'})
        self.assertEqual(created.status_code, 200)
        user_id = created.get_json()['data']['id']
        listed = self.client.get('/api/admin/users?keyword=zhang&role=user&status=1', headers=self.headers).get_json()['data']
        self.assertEqual(listed['total'], 1)
        self.assertEqual(listed['users'][0]['status'], 1)
        self.assertEqual(self.client.put(f'/api/admin/users/{user_id}', headers=self.headers, json={'nickname':'张三丰','status':0}).status_code, 200)
        self.assertEqual(self.client.put(f'/api/admin/users/{user_id}/password', headers=self.headers, json={'password':'newpass123'}).status_code, 200)

    def test_cannot_disable_or_delete_self_last_admin(self):
        self.assertEqual(self.client.put('/api/admin/users/1', headers=self.headers, json={'status':0}).status_code, 409)
        self.assertEqual(self.client.delete('/api/admin/users/1', headers=self.headers).status_code, 409)

    def test_disabled_user_cannot_login(self):
        hashed, _ = _hash_password('123456')
        db.session.add(User(username='disabled', password_hash=hashed, role='user', status=0)); db.session.commit()
        response = self.client.post('/api/auth/login', json={'username':'disabled','password':'123456'})
        self.assertEqual(response.status_code, 403)

    def test_roles_endpoint(self):
        self.assertEqual(self.client.get('/api/admin/roles', headers=self.headers).get_json()['data']['roles'], ['admin','user'])

