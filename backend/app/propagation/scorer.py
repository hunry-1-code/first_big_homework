from datetime import datetime
from app.propagation.evidence import tokens,source_evidence
def similarity(a,b):
    x,y=tokens(a),tokens(b)
    return len(x&y)/len(x|y) if x and y else 0.0
def inferred_score(parent,child):
    sim=similarity(parent,child); shared=sim
    pt=getattr(parent,'publish_time',None) or getattr(parent,'first_crawled_at',None); ct=getattr(child,'publish_time',None) or getattr(child,'first_crawled_at',None)
    hours=max(0,(ct-pt).total_seconds()/3600) if pt and ct else 168
    time_score=max(0.0,1-hours/(24*7)); sources=source_evidence(child)
    source_score=1.0 if any(x in (getattr(parent,'author','') or '') for x in sources) else 0.0
    cross=1.0 if getattr(parent,'platform',None)!=getattr(child,'platform',None) else .5
    return .35*sim+.25*shared+.20*time_score+.15*source_score+.05*cross
