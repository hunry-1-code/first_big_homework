import sys
from pathlib import Path
from datetime import timedelta
BACKEND_ROOT=Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path: sys.path.insert(0,str(BACKEND_ROOT))
from app import create_app
from app.extensions import db
from app.models import Article,Event,DailyHotRun,DailyHotItem
from app.services.event_topic_service import classify_event_topic
from app.services.event_topic_service import classify_topic_text
from app.services.daily_hot_service import serialize_daily_hot_run
from datetime import datetime,date,timezone

class C:
 TESTING=True; SECRET_KEY='x'; JWT_SECRET_KEY='x'; SQLALCHEMY_DATABASE_URI='sqlite:///:memory:'; SQLALCHEMY_TRACK_MODIFICATIONS=False; AUTO_CREATE_DB=False; TASK_RECOVER_ON_STARTUP=False; FRONTEND_ORIGINS=[]; JWT_EXPIRES_DELTA=timedelta(hours=1)

def test_daily_hot_event_is_classified_and_serialized():
 app=create_app(C)
 with app.app_context():
  db.create_all(); event=Event(title='台风登陆多地启动暴雨预警',source='daily_hot')
  db.session.add(event); db.session.flush()
  db.session.add(Article(event_id=event.id,platform='news',source_type='news',source_layer='institutional',source_role='news_report',url='https://x/a',url_hash='a',title='应急部门转移群众',clean_content='台风暴雨引发内涝并开展救援'))
  now=datetime.now(timezone.utc).replace(tzinfo=None)
  run=DailyHotRun(run_date=date.today(),status='success',attempt=1,item_count=1,config_hash='x',completed_at=now); db.session.add(run); db.session.flush()
  item=DailyHotItem(run_id=run.id,normalized_key='台风',title='台风',fused_score=1,rank=1,source_ranks={},source_payloads={},first_seen_at=now,last_seen_at=now,enrichment_status='completed',event_id=event.id)
  db.session.add(item); db.session.commit()
  result=classify_event_topic(event.id); item.topic_keywords=result['evidence']; db.session.commit()
  payload=serialize_daily_hot_run(run,limit=10,ttl_seconds=900)
  assert result['category']=='自然灾害'
  assert payload['items'][0]['category']=='自然灾害'


def test_real_hot_titles_cover_finance_sports_education_and_entertainment():
 assert classify_topic_text('国内油价17日24时或迎上涨')['category']=='经济金融'
 assert classify_topic_text('法国vs西班牙 点球破门')['category']=='体育'
 assert classify_topic_text('女生694分被清华录取')['category']=='教育'
 assert classify_topic_text('暑期档长剧裸播')['category']=='娱乐文化'
