# 中文互联网主流平台舆情数据采集方案与探测结果

## 1. 目标

课程项目要求系统具备网络爬虫能力，并能够从中文互联网主流平台获取舆情信息。微博、小红书、知乎、贴吧等平台存在登录态、验证码、安全验证和动态渲染等限制，因此本方案不以绕过反爬为目标，而是采用合规、可演示、可扩展的数据采集设计。

目标定义为：

```text
在不绕过验证码、不破解接口签名、不使用代理池冲击平台的前提下，
测试中文互联网主流平台公开入口能否获得可分析文本，
并为受限平台设计授权登录、低频采样和样例数据兜底方案。
```

## 2. 参考工具

| 工具 | 可参考点 |
| --- | --- |
| MediaCrawler | 多平台适配器、Playwright 登录态缓存、关键词搜索、评论采集、统一存储 |
| MindSpider | 舆情流程：热点发现、关键词生成、多平台采集、情感分析、入库 |
| dataabc/weiboSpider | 微博字段设计，如正文、时间、点赞、转发、评论、话题 |
| SpiderClub/weibospider | Celery 任务队列、定时任务、访问频率控制 |
| RSSHub | 稳定补充入口，可采集热榜、新闻和部分平台公开内容 |
| trafilatura | 新闻网页正文抽取、元数据抽取、RSS/sitemap 支持 |

本项目只借鉴这些项目的架构思想和字段设计，不直接照搬代码。

## 3. 推荐采集架构

```text
数据源配置
  -> 采集任务调度
  -> 平台适配器
      -> 新闻/RSS 适配器
      -> 微博适配器
      -> 小红书适配器
      -> 知乎适配器
      -> 贴吧适配器
      -> B站适配器
      -> 样例数据导入适配器
  -> 原始数据入库
  -> 清洗、去重、正文抽取
  -> 事件聚合、情感分析、趋势预测
```

平台适配器统一输出：

```json
{
  "platform": "bilibili",
  "source_url": "https://example.com/item/1",
  "title": "标题",
  "content": "正文或摘要",
  "author": "作者",
  "publish_time": "2026-07-06T10:00:00",
  "like_count": 0,
  "comment_count": 0,
  "repost_count": 0,
  "raw_json": {}
}
```

## 4. 分层数据来源

### 4.1 第一层：普通公开入口

用于低成本测试和新闻补充。

```text
B站搜索
百度新闻搜索
新闻网站搜索页
RSSHub / RSS
```

### 4.2 第二层：授权登录采样

微博、小红书、知乎、贴吧等平台普通 HTTP 请求通常拿不到稳定文本。第一版项目可以参考 MediaCrawler 的方式，采用用户手动登录或扫码后保存登录态，再低频采集公开内容。

约束：

```text
不绕过验证码
不破解接口签名
不批量注册账号
不采集非公开内容
不高频请求
```

### 4.3 第三层：样例数据兜底

用于演示和测试完整分析链路。

```text
CSV / JSON / Excel 导入
```

这样即使某个平台登录态失效，系统仍然可以演示：

```text
采集/导入 -> 清洗 -> 聚合 -> 情感分析 -> 风险评估 -> 报告生成
```

## 5. 本次公开入口探测方法

实现脚本：

```text
tools/public_crawl_probe.py
```

测试文件：

```text
tests/test_public_crawl_probe.py
```

运行命令：

```bash
python -m unittest discover -s tests
python tools/public_crawl_probe.py --keyword 舆情 --json-out crawl_probe_results.json --csv-out crawl_probe_results.csv
```

探测方式：

```text
每个目标只发起一次普通 HTTP GET 请求
请求间隔 2 秒
不带账号 Cookie
不使用代理池
不处理验证码
不逆向加密参数
```

结果分类：

| 分类 | 含义 |
| --- | --- |
| public_content_accessible | 普通请求可获取可分析文本 |
| login_or_verification_required | 返回登录、访客系统、验证码或安全验证 |
| blocked_or_rate_limited | 返回 403、429 等访问限制 |
| too_little_text | 返回内容不足，通常是动态渲染或空壳页面 |
| no_search_results | 页面可访问，但当前关键词无结果 |
| network_error | 网络层失败 |

## 6. 本次探测结果

关键词：

```text
舆情
```

| 平台入口 | HTTP 状态 | 结果 | 判断 |
| --- | ---: | --- | --- |
| 微博搜索 | 200 | login_or_verification_required | 返回 Sina Visitor System，普通请求不可用 |
| 微博热搜 | 200 | login_or_verification_required | 返回 Sina Visitor System，普通请求不可用 |
| 小红书搜索 | 200 | too_little_text | 返回大页面但无可见文本，依赖动态渲染/登录态 |
| 小红书发现页 | 200 | too_little_text | 仅返回少量标题文本 |
| 知乎搜索 | 403 | blocked_or_rate_limited | 普通请求被拒绝 |
| 知乎热榜 | 403 | blocked_or_rate_limited | 普通请求被拒绝 |
| 百度贴吧搜索 | 403 | blocked_or_rate_limited | 返回百度安全验证 |
| 百度贴吧主题吧 | 403 | blocked_or_rate_limited | 返回百度安全验证 |
| B站搜索 | 200 | public_content_accessible | 可获取搜索结果文本 |
| 百度新闻搜索 | 200 | public_content_accessible | 可获取新闻搜索结果文本 |
| 澎湃新闻搜索 | 200 | no_search_results | 页面可访问，但当前关键词无结果 |
| 人民网搜索 | 200 | too_little_text | 返回 Loading 页面，可能需要动态渲染 |

## 7. 结论

本次普通公开入口探测证明：

1. B站搜索和百度新闻搜索可以作为第一版可直接采集的数据源。
2. 微博、知乎、贴吧普通请求受限，不适合作为无登录爬虫的核心演示依赖。
3. 小红书返回的是动态页面壳，普通 HTML 解析拿不到有效内容。
4. 新闻站适合作为稳定补充源，但不同网站搜索页可解析性差异较大。

## 8. 对项目的建议

第一版系统建议这样落地：

```text
必须实现：
  B站搜索适配器
  百度新闻/新闻网页适配器
  样例数据导入适配器

建议实现：
  RSSHub/RSS 适配器
  trafilatura 新闻正文抽取

扩展实现：
  微博、小红书、知乎、贴吧授权登录低频采样适配器
```

答辩表述建议：

```text
系统已经实现中文互联网主流平台采集适配器架构。
普通公开入口测试显示，部分平台存在登录态和安全验证限制。
因此系统对微博、小红书、知乎、贴吧采用授权登录和低频采样方案，
同时使用 B站、百度新闻、RSS 和样例数据保证分析链路稳定可演示。
```

## 9. 下一步

如果课程必须现场展示微博、小红书、知乎或贴吧数据，建议下一步做：

1. 参考 MediaCrawler，引入 Playwright。
2. 手动登录平台账号，保存登录态。
3. 每个平台只采集少量公开样本。
4. 设置严格限速和任务失败降级。
5. 将成功采集到的数据保存为样例数据，保证答辩时可复现。

这样既能满足“主流媒体数据获取”的课程要求，也能避免把项目变成反爬对抗工具。
