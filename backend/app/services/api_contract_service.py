from datetime import date,datetime
PLATFORMS={'weibo_hot':'微博热搜','weibo':'微博搜索','zhihu':'知乎','zhihu_hot':'知乎','bilibili':'B站','xiaohongshu':'小红书','baidu_hot':'百度热搜','baidu':'百度搜索'}
def api_platform_name(v):return PLATFORMS.get(str(v or '').lower())
def api_lifecycle_stage(v):return v if v in {'潜伏期','成长期','高潮期','消退期'} else '潜伏期'
def clamp_ratio(v):return max(0.0,min(1.0,float(v or 0)))
def normalized_sentiment(p,n,u):
    vals=[clamp_ratio(p),clamp_ratio(n),clamp_ratio(u)];s=sum(vals)
    if s<=0:return (0.0,0.0,1.0)
    return tuple(x/s for x in vals)
def api_sentiment_label(v):return {'positive':'正面','正面':'正面','negative':'负面','负面':'负面','neutral':'中性','中立':'中性','中性':'中性'}.get(v,'中性')
def clamp_heat(v):return max(0.0,min(100.0,float(v or 0)))
def short_date(v):
    if isinstance(v,str):
        try:v=datetime.fromisoformat(v.replace('Z','+00:00'))
        except ValueError:return v
    return f'{v.month}/{v.day}' if isinstance(v,(date,datetime)) else ''
def trend_key_points(dates,counts):
    if not dates or not counts:return []
    pairs=[('首次报道',0),('热度峰值',max(range(len(counts)),key=counts.__getitem__)),('最新动态',len(counts)-1)];out=[];seen=set()
    for name,i in pairs:
        coord=(dates[i],counts[i])
        if coord not in seen:out.append({'name':name,'coord':[dates[i],counts[i]]});seen.add(coord)
    return out
