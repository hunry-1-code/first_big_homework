from __future__ import annotations

from app.crawler.base import CrawlBatch, CrawlIssue, CrawlRequest, CrawlerRegistry
from app.crawler.errors import CrawlerError


class CrawlService:
    def __init__(
        self,
        registry: CrawlerRegistry,
        default_target_count: int = 100,
        maximum_target_count: int = 200,
        preferred_platform_limit: int = 50,
    ) -> None:
        self.registry = registry
        self.default_target_count = default_target_count
        self.maximum_target_count = maximum_target_count
        self.preferred_platform_limit = preferred_platform_limit

    def collect(
        self,
        keyword: str | None,
        platforms: list[str] | None = None,
        target_count: int | None = None,
        mode: str = "search",
    ) -> CrawlBatch:
        if platforms:
            selected = platforms
        elif mode == "hot":
            selected = [name for name in self.registry.platforms() if name.endswith("_hot")]
        else:
            selected = [
                name
                for name in self.registry.platforms()
                if name not in {"sample", "rss"} and not name.endswith("_hot")
            ]
        target = min(
            self.maximum_target_count,
            max(1, int(target_count or self.default_target_count)),
        )
        batch = CrawlBatch(keyword=keyword, target_count=target)
        if not selected:
            return batch

        # 每平台配额 = min(上限, 总目标的 2 倍)
        # 允许高产平台多贡献，低产平台少占配额
        allocation = min(
            self.preferred_platform_limit,
            max(3, target * 2),
        )
        seen: set[str] = set()

        for platform in selected:
            try:
                crawler = self.registry.get(platform)
                documents = crawler.crawl(
                    CrawlRequest(
                        platform=platform,
                        keyword=keyword,
                        limit=allocation,
                        mode=mode,
                    )
                )
            except KeyError as exc:
                batch.errors.append(
                    CrawlIssue(platform, "CRAWLER_NOT_CONFIGURED", str(exc), False)
                )
                continue
            except CrawlerError as exc:
                batch.errors.append(
                    CrawlIssue(exc.platform or platform, exc.code, exc.message, exc.retryable)
                )
                continue
            except Exception as exc:
                batch.errors.append(
                    CrawlIssue(platform, "CRAWL_UNEXPECTED_ERROR", str(exc), False)
                )
                continue

            if not documents:
                batch.platform_counts[platform] = 0
                batch.errors.append(
                    CrawlIssue(
                        platform,
                        "CRAWL_EMPTY_RESPONSE",
                        "platform returned no usable documents",
                        False,
                    )
                )
                continue

            added = 0
            for document in documents:
                keys = {f"url:{document.source_url.strip().lower()}"}
                if document.source_article_id:
                    keys.add(f"source:{document.platform}:{document.source_article_id}")
                if seen.intersection(keys):
                    continue
                seen.update(keys)
                batch.documents.append(document)
                added += 1
                concrete_platform = document.platform or platform
                batch.platform_counts[concrete_platform] = (
                    batch.platform_counts.get(concrete_platform, 0) + 1
                )
                if len(batch.documents) >= target:
                    break
            source_counts = getattr(crawler, "last_source_counts", None)
            if isinstance(source_counts, dict):
                for source_platform in source_counts:
                    batch.platform_counts.setdefault(source_platform, 0)
            if len(batch.documents) >= target:
                break

        return batch
