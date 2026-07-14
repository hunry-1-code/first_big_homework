import sys
from pathlib import Path
from datetime import timedelta
BACKEND_ROOT=Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path: sys.path.insert(0,str(BACKEND_ROOT))
from app import create_app
from app.extensions import db
from app.models import Article,Comment,Event,AnalysisRunArticle
from app.crawler.comments import RawComment
from app.services.comment_service import persist_comment
from app.services.public_opinion_service import get_public_opinion_snapshot

class C:
 TESTING=True; SECRET_KEY='x'; JWT_SECRET_KEY='x'; SQLALCHEMY_DATABASE_URI='sqlite:///:memory:'; SQLALCHEMY_TRACK_MODIFICATIONS=False; AUTO_CREATE_DB=False; TASK_RECOVER_ON_STARTUP=False; FRONTEND_ORIGINS=[]; JWT_EXPIRES_DELTA=timedelta(hours=1)

def setup_function():
 global app,ctx
 app=create_app(C); ctx=app.app_context(); ctx.push(); db.create_all()

def teardown_function():
 db.session.remove(); db.drop_all(); ctx.pop()

def article(event, platform='weibo', layer='public'):
 row=Article(event_id=event.id,platform=platform,source_type='social',source_layer=layer,source_role='social_post' if layer=='public' else 'news_report',url=f'https://x/{platform}',url_hash=platform,title='标题',clean_content='内容',clean_status='success')
 db.session.add(row); db.session.commit(); return row

def test_comment_upsert_is_idempotent_and_not_an_analysis_article():
 e=Event(title='事件'); db.session.add(e); db.session.commit(); a=article(e)
 first=persist_comment(a,RawComment('weibo','c1','希望及时回应',likes_count=1))
 second=persist_comment(a,RawComment('weibo','c1','希望及时回应',likes_count=8))
 assert first.id==second.id and Comment.query.count()==1 and second.likes_count==8
 assert AnalysisRunArticle.query.count()==0

def test_public_snapshot_reports_gap_only_with_both_layers():
 e=Event(title='暴雨'); db.session.add(e); db.session.commit(); public=article(e)
 persist_comment(public,RawComment('weibo','c2','没人管，应该及时救援'))
 only=get_public_opinion_snapshot(e.id)
 assert only['analysis_mode']=='public_opinion_only' and only['narrative_gap_score'] is None
 official=article(e,'news','institutional'); official.clean_content='有关部门通报并开展救援处置'; db.session.commit()
 both=get_public_opinion_snapshot(e.id)
 assert both['analysis_mode']=='narrative_gap' and both['institutional_response_rate']==1.0
