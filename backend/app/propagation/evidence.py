import re
PARENT_KEYS=('parent_id','root_id','reposted_from','retweeted_status','quoted_status')
def explicit_parent_ids(article):
    raw=getattr(article,'raw_json',{}) or {}; values=[]
    for key in PARENT_KEYS:
        value=raw.get(key)
        if isinstance(value,dict):value=value.get('id') or value.get('mid') or value.get('source_article_id')
        if value is not None:values.append(str(value))
    return values
def source_evidence(article):
    text=' '.join(str(x or '') for x in (getattr(article,'title',''),getattr(article,'clean_content',''),getattr(article,'raw_content','')))
    hits=re.findall(r'(?:据|转自|来源[:：]?|转载自)([\u4e00-\u9fffA-Za-z0-9_-]{2,20})',text)
    return hits
def tokens(article):
    text=(getattr(article,'title','') or '')+' '+(getattr(article,'clean_content','') or '')[:300]
    chinese=''.join(re.findall(r'[\u4e00-\u9fff]',text))
    bigrams={chinese[i:i+2] for i in range(max(0,len(chinese)-1))}
    return bigrams | set(re.findall(r'[A-Za-z0-9_]{2,}',text.lower()))
