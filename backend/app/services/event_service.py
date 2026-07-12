from __future__ import annotations


SAMPLE_EVENTS = [
    {
        "id": 1,
        "title": "某知名互联网企业疑似发生大规模用户数据泄露事件",
        "summary": "近日有网民爆料称某头部互联网公司发生用户隐私数据泄露，涉及数千万用户信息，包括手机号、身份证等敏感字段已在暗网流传，引发广泛关注。",
        "heat_index": 92.3,
        "lifecycle_stage": "高潮期",
        "sentiment_positive": 0.05,
        "sentiment_negative": 0.82,
        "sentiment_neutral": 0.13,
    },
    {
        "id": 2,
        "title": "新能源汽车品牌发布新款自动驾驶系统引发热议",
        "summary": "某国产新能源汽车品牌召开发布会，宣布旗下全系车型将搭载新一代L3级自动驾驶系统，部分网友质疑其技术成熟度与安全性。",
        "heat_index": 78.6,
        "lifecycle_stage": "成长期",
        "sentiment_positive": 0.48,
        "sentiment_negative": 0.29,
        "sentiment_neutral": 0.23,
    },
    {
        "id": 3,
        "title": "某地发生食品安全事件相关部门介入调查",
        "summary": "有消费者在社交平台发布视频称在某连锁餐饮品牌就餐后出现集体腹泻症状，当地市场监管局已成立专项调查组开展核查。",
        "heat_index": 65.2,
        "lifecycle_stage": "成长期",
        "sentiment_positive": 0.08,
        "sentiment_negative": 0.74,
        "sentiment_neutral": 0.18,
    },
    {
        "id": 4,
        "title": "全国铁路暑运首周客流量创历史新高",
        "summary": "中国国家铁路集团发布数据，2026年暑运首周全国铁路累计发送旅客突破1.2亿人次，同比增长15.3%，多条热门线路加开临时列车。",
        "heat_index": 41.8,
        "lifecycle_stage": "潜伏期",
        "sentiment_positive": 0.65,
        "sentiment_negative": 0.07,
        "sentiment_neutral": 0.28,
    },
    {
        "id": 5,
        "title": "某流量明星被曝税务问题已持续发酵一周",
        "summary": "娱乐媒体连续追踪报道某顶流艺人涉嫌偷逃税款事件，粉丝群体内部出现分裂，品牌方陆续宣布暂停合作，事件热度趋于平稳回落。",
        "heat_index": 33.5,
        "lifecycle_stage": "消退期",
        "sentiment_positive": 0.15,
        "sentiment_negative": 0.61,
        "sentiment_neutral": 0.24,
    },
    {
        "id": 6,
        "title": "多地暴雨引发洪涝灾害应急响应升至二级",
        "summary": "受持续强降雨影响，长江中下游多地出现严重城市内涝和山体滑坡，国家防总已将防汛应急响应提升至二级，救援力量全面投入一线。",
        "heat_index": 88.9,
        "lifecycle_stage": "高潮期",
        "sentiment_positive": 0.12,
        "sentiment_negative": 0.56,
        "sentiment_neutral": 0.32,
    },
    {
        "id": 7,
        "title": "AI生成内容标识新规正式施行引发产学研热议",
        "summary": "国家网信办发布的《人工智能生成内容标识管理办法》今日起正式施行，要求所有AI生成内容必须添加显式标识，学术界与产业界对此展开激烈讨论。",
        "heat_index": 55.7,
        "lifecycle_stage": "成长期",
        "sentiment_positive": 0.42,
        "sentiment_negative": 0.22,
        "sentiment_neutral": 0.36,
    },
    {
        "id": 8,
        "title": "某城市推出数字人民币试点全民消费补贴活动",
        "summary": "某一线城市联合六大银行推出数字人民币消费红包发放活动，市民可通过指定APP领取最高500元数字人民币红包，引发市民排队体验。",
        "heat_index": 28.4,
        "lifecycle_stage": "潜伏期",
        "sentiment_positive": 0.71,
        "sentiment_negative": 0.04,
        "sentiment_neutral": 0.25,
    },
    {
        "id": 9,
        "title": "某上市公司财务造假丑闻被做空机构曝光",
        "summary": "国际知名做空机构发布长篇调查报告，指控某A股上市公司存在系统性财务造假行为，该公司股价当日跌停，证监会表示已启动核查程序。",
        "heat_index": 85.1,
        "lifecycle_stage": "高潮期",
        "sentiment_positive": 0.03,
        "sentiment_negative": 0.89,
        "sentiment_neutral": 0.08,
    },
    {
        "id": 10,
        "title": "国产大型客机成功完成首次跨洋商业航线飞行",
        "summary": "国产C919大型客机首次执飞上海至新加坡国际商业航线并顺利抵达，标志着国产大飞机在国际化运营道路上迈出关键一步。",
        "heat_index": 52.3,
        "lifecycle_stage": "成长期",
        "sentiment_positive": 0.78,
        "sentiment_negative": 0.03,
        "sentiment_neutral": 0.19,
    },
]


def list_events(args) -> dict:
    page = int(args.get("page", 1))
    size = int(args.get("size", 20))
    keyword = args.get("keyword", "").strip()
    if keyword:
        filtered = [e for e in SAMPLE_EVENTS if keyword in e["title"]]
    else:
        filtered = list(SAMPLE_EVENTS)
    total = len(filtered)
    start = (page - 1) * size
    paged = filtered[start : start + size]
    return {"events": paged, "total": total, "page": page, "size": size}


def get_event_detail(event_id: int) -> dict:
    event = next((e for e in SAMPLE_EVENTS if e["id"] == event_id), SAMPLE_EVENTS[0])
    event = {**event, "id": event_id}
    return {
        **event,
        "report": {
            "overview_text": "报告内容由后台 report 任务生成，这里是接口占位。",
            "risk_data": {"level": "中风险", "score": 55},
        },
        "trend": {"dates": ["2026-07-08", "2026-07-09"], "counts": [12, 35], "key_points": []},
        "sentiment": {
            "positive": event["sentiment_positive"],
            "negative": event["sentiment_negative"],
            "neutral": event["sentiment_neutral"],
            "daily": [],
        },
        "platform": {"platforms": [{"name": "样例数据", "count": 47, "percentage": 1.0}]},
        "keywords": {
            "keywords": [
                {"word": "舆情", "weight": 0.95},
                {"word": "安全", "weight": 0.88},
                {"word": "网络", "weight": 0.82},
                {"word": "监测", "weight": 0.76},
                {"word": "热点", "weight": 0.71},
                {"word": "传播", "weight": 0.65},
                {"word": "大V转发", "weight": 0.58},
                {"word": "评论区", "weight": 0.53},
                {"word": "热度指数", "weight": 0.49},
                {"word": "负面情感", "weight": 0.44},
                {"word": "研判报告", "weight": 0.39},
                {"word": "谣言检测", "weight": 0.34},
                {"word": "置信度", "weight": 0.30},
                {"word": "数据清洗", "weight": 0.26},
                {"word": "博主", "weight": 0.22},
                {"word": "系统预警", "weight": 0.18},
                {"word": "敏感词", "weight": 0.15},
                {"word": "公关", "weight": 0.12}
            ]
        },
        "articles": {
            "articles": [
                {
                    "id": 1, "platform": "微博热搜", "title": "网传某平台用户数据遭泄露，官方尚未回应",
                    "author": "科技圈那些事", "publish_time": "2026-07-11 14:20",
                    "reposts_count": 4521, "comments_count": 2830, "likes_count": 12056,
                    "clean_content": "近日有网友爆料称某大型互联网平台发生用户数据泄露事件，涉及数千万用户信息。截至目前官方尚未发布正式声明，引发广泛关注。",
                    "sentiment_label": "负面", "is_suspicious": False, "suspicious_score": 0
                },
                {
                    "id": 2, "platform": "知乎", "title": "如何看待某平台疑似数据泄露？技术层面分析可能原因",
                    "author": "后端工程师小王", "publish_time": "2026-07-11 16:45",
                    "reposts_count": 892, "comments_count": 1560, "likes_count": 3420,
                    "clean_content": "从技术角度来看，大规模数据泄露通常与以下几个方面有关：数据库配置不当、API权限控制缺失、内部人员操作等。需要等待官方调查结果。",
                    "sentiment_label": "中立", "is_suspicious": False, "suspicious_score": 0
                },
                {
                    "id": 3, "platform": "B站", "title": "【速报】某平台千万用户数据疑在暗网出售",
                    "author": "科技观察猿", "publish_time": "2026-07-11 12:10",
                    "reposts_count": 2300, "comments_count": 4200, "likes_count": 18900,
                    "clean_content": "据暗网监测账号消息，有人声称持有某平台完整用户数据库并在暗网论坛挂牌出售。安全研究人员正在进行验证，提醒用户及时修改密码。",
                    "sentiment_label": "负面", "is_suspicious": True, "suspicious_score": 0.65
                },
                {
                    "id": 4, "platform": "百度热搜", "title": "某平台数据安全事件持续发酵，相关部门已介入",
                    "author": "新华网", "publish_time": "2026-07-11 18:00",
                    "reposts_count": 6700, "comments_count": 3210, "likes_count": 8500,
                    "clean_content": "记者今日从有关部门获悉，针对近期网络上关于某互联网平台用户数据泄露的相关报道，监管部门已经启动调查程序，后续结果将及时向社会公布。",
                    "sentiment_label": "中立", "is_suspicious": False, "suspicious_score": 0
                },
                {
                    "id": 5, "platform": "小红书", "title": "教大家自查账号是否在这次泄露事件中受影响",
                    "author": "数码生活家", "publish_time": "2026-07-11 15:30",
                    "reposts_count": 5600, "comments_count": 7800, "likes_count": 22300,
                    "clean_content": "今天看到新闻说某平台数据疑似泄露，整理了几个自查方法分享给大家，可以确认自己的信息是否在泄露范围内。",
                    "sentiment_label": "中立", "is_suspicious": False, "suspicious_score": 0
                },
            ],
            "total": 5,
        },
    }


def search_events(keyword: str) -> list[dict]:
    if not keyword:
        return SAMPLE_EVENTS
    return [e for e in SAMPLE_EVENTS if keyword in e["title"]]

