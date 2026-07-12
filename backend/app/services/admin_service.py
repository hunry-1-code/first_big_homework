import re
from datetime import timezone
from sqlalchemy import or_
from app.extensions import db
from app.models import User
from app.api.auth import _hash_password
class AdminError(ValueError):
    def __init__(self,message,status=400): super().__init__(message); self.status=status
def _iso(v):
    if not v:return None
    if v.tzinfo is None:v=v.replace(tzinfo=timezone.utc)
    return v.isoformat().replace('+00:00','Z')
def serialize_user(u):return {'id':u.id,'username':u.username,'nickname':u.nickname or u.username,'role':u.role or 'user','status':int(u.status),'last_login_at':_iso(u.last_login_at),'created_at':_iso(u.created_at)}
def _role(v):
    if v not in {'admin','user'}:raise AdminError('角色无效')
def _admins():return User.query.filter_by(role='admin',status=1).count()
def list_users(args):
    page=max(1,int(args.get('page',1)));size=min(100,max(1,int(args.get('size',20))));q=User.query;k=(args.get('keyword') or '').strip()
    if k:q=q.filter(or_(User.username.ilike(f'%{k}%'),User.nickname.ilike(f'%{k}%')))
    if args.get('role'):_role(args['role']);q=q.filter_by(role=args['role'])
    if args.get('status') not in (None,''):
        s=int(args['status']);
        if s not in (0,1):raise AdminError('状态无效')
        q=q.filter_by(status=s)
    total=q.count();rows=q.order_by(User.id).offset((page-1)*size).limit(size).all();return {'users':[serialize_user(u) for u in rows],'total':total,'page':page,'size':size}
def create_user(p):
    n=str(p.get('username','')).strip();pw=str(p.get('password',''));r=p.get('role','user');_role(r)
    if not re.fullmatch(r'[A-Za-z0-9_-]{3,50}',n):raise AdminError('用户名格式无效')
    if not 6<=len(pw)<=128:raise AdminError('密码长度必须为6到128位')
    if User.query.filter_by(username=n).first():raise AdminError('用户名已存在',409)
    u=User(username=n,password_hash=_hash_password(pw)[0],nickname=str(p.get('nickname') or '')[:50] or None,role=r,status=int(p.get('status',1)));db.session.add(u);db.session.commit();return {'id':u.id}
def update_user(uid,p,cid):
    u=db.session.get(User,uid)
    if not u:raise AdminError('用户不存在',404)
    r=p.get('role',u.role);s=int(p.get('status',u.status));_role(r)
    if s not in (0,1):raise AdminError('状态无效')
    if uid==cid and s==0:raise AdminError('不能停用自己',409)
    if u.role=='admin' and u.status==1 and (r!='admin' or s==0) and _admins()<=1:raise AdminError('不能移除最后一个启用管理员',409)
    if 'nickname' in p:u.nickname=str(p['nickname'] or '')[:50] or None
    u.role=r;u.status=s;db.session.commit();return serialize_user(u)
def reset_password(uid,pw):
    u=db.session.get(User,uid)
    if not u:raise AdminError('用户不存在',404)
    if not 6<=len(pw)<=128:raise AdminError('密码长度必须为6到128位')
    u.password_hash=_hash_password(pw)[0];db.session.commit()
def delete_user(uid,cid):
    u=db.session.get(User,uid)
    if not u:raise AdminError('用户不存在',404)
    if uid==cid:raise AdminError('不能删除自己',409)
    if u.role=='admin' and u.status==1 and _admins()<=1:raise AdminError('不能删除最后一个启用管理员',409)
    db.session.delete(u);db.session.commit()
