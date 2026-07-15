from datetime import date, datetime


PLATFORMS = {
    "weibo_hot": "微博热搜",
    "weibo": "微博搜索",
    "zhihu": "知乎",
    "zhihu_hot": "知乎",
    "bilibili": "B站",
    "xiaohongshu": "小红书",
    "douyin": "抖音",
    "baidu_hot": "百度热搜",
    "baidu": "百度搜索",
    "baidu_news": "主流媒体",
    "rss_36kr": "36氪",
    "mainstream_news": "主流新闻网站",
    "news_people": "人民网",
    "news_36kr": "36氪",
    "news_thepaper": "澎湃新闻",
    "news_infoq": "InfoQ",
    "news_sspai": "少数派",
}

LIFECYCLE_STAGES = {"潜伏期", "成长期", "高潮期", "消退期"}

SENTIMENT_LABELS = {
    "positive": "正面",
    "正面": "正面",
    "negative": "负面",
    "负面": "负面",
    "neutral": "中立",
    "中立": "中立",
    "中性": "中立",
}


def api_platform_name(v):
    return PLATFORMS.get(str(v or "").lower())


def api_lifecycle_stage(v):
    return v if v in LIFECYCLE_STAGES else "潜伏期"


def clamp_ratio(v):
    return max(0.0, min(1.0, float(v or 0)))


def normalized_sentiment(p,n,u):
    vals=[clamp_ratio(p),clamp_ratio(n),clamp_ratio(u)];s=sum(vals)
    if s<=0:return (0.0,0.0,1.0)
    return tuple(x/s for x in vals)


def api_sentiment_label(v):
    return SENTIMENT_LABELS.get(v, "中立")


def clamp_heat(v):return max(0.0,min(100.0,float(v or 0)))
def short_date(v):
    if isinstance(v,str):
        try:v=datetime.fromisoformat(v.replace('Z','+00:00'))
        except ValueError:return v
    return f'{v.month}/{v.day}' if isinstance(v,(date,datetime)) else ''
def trend_key_points(dates,counts):
    if not dates or not counts:return []
    n=len(counts)
    pairs=[(f'首次出现（{counts[0]}篇）',0),
           (f'峰值（{max(counts)}篇）',max(range(n),key=counts.__getitem__)),
           (f'最近（{counts[-1]}篇）',n-1)];out=[];seen=set()
    for name,i in pairs:
        coord=(dates[i],counts[i])
        if coord not in seen:out.append({'name':name,'coord':[dates[i],counts[i]]});seen.add(coord)
    return out
