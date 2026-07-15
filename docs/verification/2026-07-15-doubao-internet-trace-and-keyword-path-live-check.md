# 豆包全网溯源与关键词传播路径真实验证报告

## 1. 验证目标

- 事件溯源只使用豆包火山方舟 Web Search，不使用 DeepSeek 联网能力。
- DeepSeek 的评论情感、生命周期及其他分析配置保持不变。
- 传播图不再展示大量文章节点，而是由一个全网溯源节点和词云频率最高的五个关键词组成。
- 图中必须存在有方向的传播路径；每条路径包含理由、置信度和可用的证据 URL。
- 豆包无法确认真正首发时必须明确使用“疑似来源”，不得输出绝对首发结论。

## 2. 豆包配置与模型

- API：`https://ark.cn-beijing.volces.com/api/v3/responses`
- 模型：`doubao-seed-2-1-pro-260628`
- 工具：`{"type":"web_search","limit":10}`
- API Key：已配置，报告不记录密钥。
- 豆包联网超时：`180` 秒；真实搜索耗时约55–107秒，不能与DeepSeek的普通推理超时共用。
- DeepSeek：仍使用原有 `LLM_API_KEY / https://api.deepseek.com / deepseek-chat`，本次未修改。

## 3. 独立 Web Search 实测

### 输入

```text
请联网搜索2026年7月最近公开发布的人工智能新闻，列出来源标题、发布时间和原始网页URL。
```

### 输出摘要

- 请求成功。
- 返回模型：`doubao-seed-2-1-pro-260628`。
- 搜索调用：2 次。
- 引用 URL：8 条。
- 搜索结果包含2026年7月的新华社、人民网、中国新闻网和 OpenAI 等公开网页。

引用样例：

1. [超300款AI新品将在2026世界人工智能大会首发](http://www3.xinhuanet.com/tech/20260708/fbbd5fbe39b5452098b5dde915b0c959/c.html)
2. [AI造福人类全球峰会聚焦实际应用](http://finance.people.com.cn/n1/2026/0712/c1004-40758685.html)
3. [新华社消息：习近平将出席2026世界人工智能大会](http://www.xinhuanet.com/politics/leaders/20260713/c381cd933a4f499eb376526e04b35117/c.html)
4. [OpenAI News](https://openai.com/news/?author=openai#results)
5. [人工智能蓬勃兴起，锻造高质量发展新引擎](http://www.chinanews.com.cn/gn/2026/07-14/10659080.shtml)

## 4. 真实事件输入

- 事件 ID：`4`
- 事件标题：`人工智能发展动态与挑战`
- 系统已关联报道：9 篇
- 词云按权重从高到低取前五项：

| 顺序 | 关键词 | 权重 |
|---:|---|---:|
| 1 | 人工智能 | 1.0000 |
| 2 | 世界人工智能大会 | 0.9717 |
| 3 | 北京 | 0.9433 |
| 4 | 中英合作 | 0.9150 |
| 5 | 剑桥大学 | 0.8867 |

提交给豆包的核心要求：检索该事件的疑似最早公开来源，分析上述五个高频词之间的传播联系，以 JSON 返回源头、路径理由、置信度和证据 URL，不得将无法确认的来源表述为绝对首发。

## 5. 全网溯源输出

- 状态：`success`
- 方法：`doubao_web_search`
- 范围：`internet_web_search`
- 搜索引用：10 条
- 疑似来源：`剑桥中英人工智能商业论坛探讨人工智能发展新机遇`
- 来源名称：`人民网（新浪看点转载）`
- 发布时间：`2026-07-15 07:40:00`
- URL：https://k.sina.cn/article_7857201856_1d45362c00190854xu.html
- 置信度：`0.65`

豆包的限制性结论：当前没有检索到与事件标题完全匹配的独立首发内容，只能把上述报道作为目前检索范围内的疑似来源，不能确认绝对首发。

其他溯源证据包括：

- [2026世界人工智能大会亮点全解析](https://cj.sina.cn/articles/view/7880068235/1d5b04c8b01902arda)
- [英国剑桥大学校长率团访问北京大学](https://www.oir.pku.edu.cn/info/1035/9414.htm)
- [破冰之旅：中英AI合作迎来黄金时代？](https://www.sohu.com/a/982383596_530597)
- [Stanford HAI发布《2026年人工智能指数报告》](https://cingai.nankai.edu.cn/2026/0629/c10233a599277/page.htm)

## 6. 传播图输出

- 图模式：`focused_keyword_path`
- 节点数：6
- 有向边数：5
- 豆包证据边：5
- 规则补充边：0
- 结论：不存在“只有节点没有路径”的情况。

### 节点

| 节点 | 类型 | 数据来源 |
|---|---|---|
| 人民网（新浪看点转载） | 疑似源头 | 豆包全网搜索 |
| 人工智能 | 高频词 | 事件词云 Top 1 |
| 世界人工智能大会 | 高频词 | 事件词云 Top 2 |
| 北京 | 高频词 | 事件词云 Top 3 |
| 中英合作 | 高频词 | 事件词云 Top 4 |
| 剑桥大学 | 高频词 | 事件词云 Top 5 |

### 有向路径

1. `疑似源头 → 人工智能`
   - 置信度：0.65
   - 证据：疑似来源同时覆盖人工智能发展、挑战、中英合作和剑桥大学相关议题。
   - URL：https://k.sina.cn/article_7857201856_1d45362c00190854xu.html

2. `人工智能 → 世界人工智能大会`
   - 置信度：0.90
   - 理由：人工智能发展与挑战是2026世界人工智能大会的核心讨论对象。
   - URL：https://cj.sina.cn/articles/view/7880068235/1d5b04c8b01902arda

3. `世界人工智能大会 → 北京`
   - 置信度：0.95
   - 理由：大会在北京举办，北京成为相关政策、成果和讨论的集中传播节点。

4. `北京 → 中英合作`
   - 置信度：0.80
   - 理由：北京是中英人工智能学术交流和产业合作的重要对接节点。
   - URL：https://www.oir.pku.edu.cn/info/1035/9414.htm

5. `中英合作 → 剑桥大学`
   - 置信度：0.85
   - 理由：剑桥中英人工智能商业论坛是中英AI合作议题的重要交流和传播载体。
   - URL：https://k.sina.cn/article_7857201856_1d45362c00190854xu.html

## 7. 失败降级验证

当豆包 Key、模型或 Web Search 插件不可用时：

- 不创建虚假的互联网源头节点；
- 返回 `origin_analysis.status=unavailable`；
- 保留词云 Top 5 节点；
- 使用关键词频率与事件内共现关系生成4条基础有向路径；
- 路径标记为 `keyword_frequency_rule`，与豆包证据边严格区分。

## 8. 自动测试

聚焦测试：

```text
27 passed
```

覆盖豆包 Responses API请求格式、引用解析、缺少Key、六节点图、强制有向边和失败降级。

完整后端测试：

```text
363 passed, 5 warnings
```

静态编译：

```text
python -m compileall -q app scripts
exit code 0
```

警告均为既有第三方 `pkg_resources` 弃用提示和 SQLAlchemy `Query.get()` 旧接口提示，不影响本次功能。

## 9. 用户检查方式

服务重启后打开：

```text
http://localhost:8848/#/events/4
```

或请求：

```text
GET http://127.0.0.1:5000/api/events/4/propagation
```

重点检查：

1. 节点总数是否为6；
2. 是否只包含一个疑似来源和五个词云高频词；
3. 图中是否有5条带箭头的路径；
4. `origin_analysis.citations` 是否包含真实URL；
5. 每条边是否有 `evidence`、`evidence_type`、`confidence` 和 `evidence_urls`；
6. 是否使用“疑似来源”而不是无证据宣称“绝对首发”。

## 10. 运行中 HTTP 最终验证

后端重启加载新代码后，通过登录态请求正式接口：

```text
GET /api/events/4/propagation
```

最后一次验证结果：

```json
{
  "http_status": 200,
  "graph_mode": "focused_keyword_path",
  "origin_status": "success",
  "citation_count": 10,
  "node_count": 6,
  "edge_count": 5,
  "all_directed": true,
  "all_have_evidence": true
}
```

最后一次检索返回的疑似来源 URL 为：

```text
https://www.sdbdra.cn/newsinfo/11126238.html
```

豆包 Web Search 是实时检索，同一事件在不同时间请求时，候选来源、排序和 URL 可能变化。因此报告第5、6节保留第一次成功实测的完整输入输出，当前接口以每次返回的 `origin_analysis.citations`、`origin.reason` 和置信度为准。系统始终将其标记为“疑似来源”，不保证绝对首发。
