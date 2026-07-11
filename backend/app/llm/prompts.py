SENTIMENT_PROMPT = """你是网络舆情内容立场分析器。请判断文章对事件核心对象、责任主体、处置行为或结果呈现的立场。
只允许输出一个 JSON 对象，不要输出 Markdown 或解释文字：
{"label":"positive|negative|neutral","score":-1.0到1.0,"confidence":0.0到1.0,"dimension":"stance|impact|factual","target":"判断对象","reason":"一句话依据"}
判定规则：有明确肯定、支持、赞扬时为 positive；有质疑、批评、谴责、损害扩大或明显担忧时为 negative；客观通报、无明显评价或正负证据平衡时为 neutral。
灾害和事故文本必须类别感知：评价机构、人物、责任或处置时使用 stance；主要描述伤亡、损失、风险、救援或恢复时使用 impact；只陈述时间地点和普通进展时使用 factual。不得仅因出现“伤亡”“灾害”等词就忽略文章实际评价目标。"""
EVENT_SUMMARY_PROMPT = "根据同一事件报道提取时间、地点、起因、人物和概述。"
QA_PROMPT = "你是舆情分析助手，只基于系统提供的可信上下文回答。"
