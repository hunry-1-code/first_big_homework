from flask import Blueprint,g,request
from app.core.response import ok,fail
from app.core.security import admin_required
from app.services.admin_service import *
admin_bp=Blueprint('admin',__name__)
def handle(fn):
    try:return fn()
    except AdminError as e:return fail(str(e),e.status)
@admin_bp.get('/users')
@admin_required
def users():return handle(lambda:ok(list_users(request.args)))
@admin_bp.post('/users')
@admin_required
def add():return handle(lambda:ok(create_user(request.get_json(silent=True) or {})))
@admin_bp.put('/users/<int:uid>')
@admin_required
def edit(uid):return handle(lambda:ok(update_user(uid,request.get_json(silent=True) or {},g.current_user['id']),'更新成功'))
@admin_bp.put('/users/<int:uid>/password')
@admin_required
def password(uid):return handle(lambda:(reset_password(uid,str((request.get_json(silent=True) or {}).get('password',''))),ok(message='密码重置成功'))[1])
@admin_bp.delete('/users/<int:uid>')
@admin_required
def delete(uid):return handle(lambda:(delete_user(uid,g.current_user['id']),ok(message='删除成功'))[1])
@admin_bp.get('/roles')
@admin_required
def roles():return ok({'roles':['admin','user']})
