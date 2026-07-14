from collections import Counter
from app.extensions import db
from app.models import Article, Event

CATEGORY_RULES = {
    "政治政务": ("政府", "政策", "会议", "人大", "政协", "外交", "选举", "总统", "部长", "通报"),
    "经济金融": ("经济", "股市", "银行", "基金", "房价", "汇率", "关税", "企业", "融资", "消费"),
    "社会民生": ("民生", "就业", "住房", "社区", "居民", "婚姻", "养老", "权益", "纠纷"),
    "公共安全": ("事故", "火灾", "警方", "犯罪", "救援", "失踪", "坍塌", "爆炸", "安全"),
    "自然灾害": ("台风", "暴雨", "地震", "洪水", "山火", "泥石流", "灾害", "内涝", "预警"),
    "科技互联网": ("人工智能", "AI", "芯片", "手机", "互联网", "机器人", "软件", "算法", "航天"),
    "教育": ("学校", "高考", "大学", "学生", "教师", "教育", "考试", "招生"),
    "医疗健康": ("医院", "医生", "疾病", "药品", "医疗", "健康", "疫苗", "患者"),
    "体育": ("比赛", "冠军", "足球", "篮球", "奥运", "运动员", "联赛", "国足", "网球"),
    "娱乐文化": ("电影", "电视剧", "明星", "演员", "歌手", "综艺", "演唱会", "票房", "音乐"),
    "消费生活": ("食品", "餐饮", "旅游", "购物", "品牌", "价格", "家居", "宠物", "穿搭"),
    "交通出行": ("铁路", "航班", "地铁", "高速", "交通", "列车", "机场", "公交"),
    "国际事件": ("美国", "俄罗斯", "日本", "欧洲", "联合国", "战争", "国际", "海外", "冲突"),
}

def classify_event_topic(event_id: int) -> dict:
    event = db.session.get(Event, int(event_id))
    if event is None: raise KeyError(f"event not found: {event_id}")
    articles = Article.query.filter_by(event_id=event.id).limit(100).all()
    text = " ".join([event.title or "", event.summary or ""] + [f"{a.title or ''} {a.clean_content or ''}" for a in articles])[:30000]
    scores = Counter({category: sum(text.count(term) for term in terms) for category, terms in CATEGORY_RULES.items()})
    category, score = scores.most_common(1)[0] if scores else ("其他", 0)
    if score <= 0: category = "其他"
    total = sum(scores.values())
    confidence = round(score / total, 4) if total and score else 0.0
    evidence = [term for term in CATEGORY_RULES.get(category, ()) if term in text][:8]
    event.topic_category = category
    event.topic_name = event.title[:100]
    db.session.commit()
    return {"category": category, "topic_name": event.topic_name, "confidence": confidence, "method": "event_rule_v1", "evidence": evidence}
