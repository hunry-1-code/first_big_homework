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
from app.services.public_opinion_service import get_public_opinion_snapshot, upgrade_comment_sentiments

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

def test_comment_upsert_does_not_overwrite_existing_llm_result():
 e=Event(title='事件'); db.session.add(e); db.session.commit(); a=article(e)
 row=persist_comment(a,RawComment('weibo','llm-keep','原评论',likes_count=1))
 row.sentiment_label='negative'; row.sentiment_score=-0.8; row.analysis_status='llm'; db.session.commit()

 updated=persist_comment(a,RawComment('weibo','llm-keep','原评论',likes_count=9))

 assert updated.likes_count==9
 assert updated.sentiment_label=='negative'
 assert updated.sentiment_score==-0.8
 assert updated.analysis_status=='llm'

def test_public_snapshot_reports_gap_only_with_both_layers():
 e=Event(title='暴雨'); db.session.add(e); db.session.commit(); public=article(e)
 persist_comment(public,RawComment('weibo','c2','没人管，应该及时救援'))
 only=get_public_opinion_snapshot(e.id)
 assert only['analysis_mode']=='public_opinion_only' and only['narrative_gap_score'] is None
 official=article(e,'news','institutional'); official.clean_content='有关部门通报并开展救援处置'; db.session.commit()
 both=get_public_opinion_snapshot(e.id)
 assert both['analysis_mode']=='narrative_gap' and both['institutional_response_rate']==1.0

def test_event_comment_upgrade_covers_all_platforms_and_records_provenance(monkeypatch):
 e=Event(title='张雪峰事件'); db.session.add(e); db.session.commit()
 bilibili=article(e,'bilibili'); news=article(e,'news_thepaper','institutional')
 first=persist_comment(bilibili,RawComment('bilibili','b1','这段分析很有道理'))
 second=persist_comment(news,RawComment('news_thepaper','n1','仍然需要进一步回应'))
 monkeypatch.setattr(
  'app.analysis.sentiment_analyzer.analyze_comments_batch',
  lambda rows: {
   first.id:{'label':'positive','score':0.7,'method':'llm_batch'},
   second.id:{'label':'neutral','score':0.0,'method':'snownlp_fallback'},
  },
 )

 result=upgrade_comment_sentiments(e.id)

 assert result=={'selected':2,'llm':1,'snownlp_fallback':1,'failed':0}
 assert db.session.get(Comment,first.id).analysis_status=='llm'
 assert db.session.get(Comment,second.id).analysis_status=='snownlp_fallback'

def test_event_comment_upgrade_skips_existing_llm_rows(monkeypatch):
 e=Event(title='事件'); db.session.add(e); db.session.commit(); a=article(e,'bilibili')
 row=persist_comment(a,RawComment('bilibili','b2','已经分析'))
 row.analysis_status='llm'; db.session.commit()
 called=[]
 monkeypatch.setattr('app.analysis.sentiment_analyzer.analyze_comments_batch',lambda rows: called.append(rows) or {})

 result=upgrade_comment_sentiments(e.id)

 assert result=={'selected':0,'llm':0,'snownlp_fallback':0,'failed':0}
 assert called==[]

def test_event_comment_upgrade_processes_more_than_one_hundred_rows(monkeypatch):
 e=Event(title='大事件'); db.session.add(e); db.session.commit(); a=article(e,'bilibili')
 for index in range(101):
  persist_comment(a,RawComment('bilibili',f'many-{index}',f'评论{index}'))
 monkeypatch.setattr(
  'app.analysis.sentiment_analyzer.analyze_comments_batch',
  lambda rows:{row['id']:{'label':'neutral','score':0.0,'method':'llm_batch'} for row in rows},
 )

 result=upgrade_comment_sentiments(e.id)

 assert result['selected']==101
 assert result['llm']==101
 assert Comment.query.filter_by(analysis_status='llm').count()==101
