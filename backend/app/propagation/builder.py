from app.propagation.evidence import explicit_parent_ids
from app.propagation.scorer import inferred_score
from app.propagation.phases import classify
def _time(a):return getattr(a,'publish_time',None) or getattr(a,'first_crawled_at',None)
def _interactions(a):return sum((getattr(a,x,0) or 0) for x in ('likes_count','comments_count','reposts_count','views_count'))
def build_propagation_graph(articles,platform_mapper=lambda x:x,max_nodes=40):
    rows=sorted(articles,key=lambda a:(_time(a) is None,_time(a),a.id)); by_source={str(getattr(a,'source_article_id','')):a for a in rows}; links=[]; incoming=set()
    for index,child in enumerate(rows):
        explicit=next((by_source[x] for x in explicit_parent_ids(child) if x in by_source and by_source[x].id!=child.id),None)
        if explicit and (_time(explicit) is None or _time(child) is None or _time(explicit)<=_time(child)):
            links.append({'source':explicit.id,'target':child.id,'relation_type':'repost_or_quote','evidence_type':'explicit','confidence':1.0,'evidence':['平台原始转发或引用关系'],'time_gap_hours':((_time(child)-_time(explicit)).total_seconds()/3600 if _time(child) and _time(explicit) else None)});incoming.add(child.id);continue
        candidates=[]
        for parent in rows[:index]:
            score=inferred_score(parent,child)
            if score>=.38:candidates.append((score,parent))
        if candidates:
            score,parent=max(candidates,key=lambda x:(x[0],_time(x[1]) or 0))
            links.append({'source':parent.id,'target':child.id,'relation_type':'cross_platform_followup' if parent.platform!=child.platform else 'content_followup','evidence_type':'inferred','confidence':round(score,3),'evidence':[f'综合证据得分 {score:.2f}'],'time_gap_hours':round((_time(child)-_time(parent)).total_seconds()/3600,2) if _time(child) and _time(parent) else None});incoming.add(child.id)
    roots={a.id for a in rows if a.id not in incoming}; first_platform={}
    for a in rows:first_platform.setdefault(a.platform,a.id)
    peak=max(rows,key=_interactions).id if rows else None;nodes=[];key_nodes=[];phases=[]
    for a in rows[:max_nodes]:
        kind,reasons=classify(a,a.id in roots,first_platform.get(a.platform)==a.id,a.id==peak)
        node={'id':a.id,'article_id':a.id,'name':getattr(a,'author',None) or '匿名用户','title':getattr(a,'title',''),'platform':platform_mapper(a.platform) or a.platform,'publish_time':_time(a).isoformat() if _time(a) else None,'time_confidence':'high' if getattr(a,'publish_time',None) else 'low','node_type':kind,'category':kind,'interaction_count':_interactions(a),'symbolSize':18+min(24,_interactions(a)**.25),'is_key_node':kind!='ordinary' or bool(reasons),'key_node_reasons':reasons}
        nodes.append(node)
        if node['is_key_node']:key_nodes.append(node)
    for node in key_nodes:
        if node['node_type'] in {'origin_candidate','influencer_amplification','media_intervention','official_response','peak_content'}:phases.append({'phase_type':node['node_type'],'time':node['publish_time'],'representative_node_id':node['id'],'title':node['title']})
    ids={n['id'] for n in nodes};links=[x for x in links if x['source'] in ids and x['target'] in ids]
    return {'summary':{'node_count':len(nodes),'edge_count':len(links),'explicit_edge_count':sum(x['evidence_type']=='explicit' for x in links),'inferred_edge_count':sum(x['evidence_type']=='inferred' for x in links),'origin_candidate_count':len(roots),'platforms':sorted({n['platform'] for n in nodes}),'coverage_notice':'仅反映当前已采集公开数据，虚线关系为算法推测'},'key_nodes':key_nodes,'phases':phases,'graph':{'nodes':nodes,'links':links,'secondary_links':[]}}
