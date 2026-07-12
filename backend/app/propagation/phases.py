from app.analysis.fake_detector import _match_official_media
def classify(article,is_root=False,is_platform_first=False,is_peak=False):
    author=getattr(article,'author','') or ''; title=(getattr(article,'title','') or '')+(getattr(article,'clean_content','') or '')[:100]
    reasons=[]; kind='ordinary'
    if is_root:kind='origin_candidate';reasons.append('当前数据中的源头候选')
    if is_platform_first:reasons.append('该平台首次出现')
    if _match_official_media(author):kind='media_intervention';reasons.append('媒体介入')
    if getattr(article,'author_type',None) in {'official','government','官方机构'} or any(x in title for x in ('官方回应','通报','辟谣')):kind='official_response';reasons.append('官方回应')
    elif (getattr(article,'author_followers',0) or 0)>=500000 and not _match_official_media(author):kind='influencer_amplification';reasons.append('高影响力账号放大')
    if is_peak and kind=='ordinary':kind='peak_content';reasons.append('互动量峰值')
    return kind,reasons
