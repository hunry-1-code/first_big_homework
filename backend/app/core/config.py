import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv


BACKEND_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(BACKEND_ROOT / ".env")


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", SECRET_KEY)
    JWT_EXPIRES_DELTA = timedelta(hours=int(os.getenv("JWT_EXPIRES_HOURS", "24")))

    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///opinion_analysis_dev.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    AUTO_CREATE_DB = os.getenv("AUTO_CREATE_DB", "true").lower() == "true"

    FRONTEND_ORIGINS = [
        origin.strip()
        for origin in os.getenv("FRONTEND_ORIGIN", "http://localhost:5173").split(",")
        if origin.strip()
    ]

    DEMO_ADMIN_USERNAME = os.getenv("DEMO_ADMIN_USERNAME", "admin")
    DEMO_ADMIN_PASSWORD = os.getenv("DEMO_ADMIN_PASSWORD", "admin123")

    TIKHUB_API_KEY = os.getenv("TIKHUB_API_KEY", "")
    TIKHUB_BASE_URL = os.getenv("TIKHUB_BASE_URL", "https://api.tikhub.io")
    TIKHUB_ENABLED_PLATFORMS = [
        platform.strip()
        for platform in os.getenv(
            "TIKHUB_ENABLED_PLATFORMS", "weibo,xiaohongshu,douyin"
        ).split(",")
        if platform.strip()
    ]
    TIKHUB_PLATFORM_API_KEYS = {
        "weibo": os.getenv("TIKHUB_WEIBO_API_KEY", ""),
        "xiaohongshu": os.getenv("TIKHUB_XIAOHONGSHU_API_KEY", ""),
        "douyin": os.getenv("TIKHUB_DOUYIN_API_KEY", ""),
        "zhihu": os.getenv("TIKHUB_ZHIHU_API_KEY", ""),
    }
    COMMENT_MAX_PER_ARTICLE = min(200, max(1, int(os.getenv("COMMENT_MAX_PER_ARTICLE", "50"))))
    COMMENT_MAX_REPLIES = min(100, max(0, int(os.getenv("COMMENT_MAX_REPLIES", "20"))))
    BILIBILI_FETCH_DANMAKU = os.getenv("BILIBILI_FETCH_DANMAKU", "false").lower() == "true"

    ZHIHU_API_BASE_URL = os.getenv(
        "ZHIHU_API_BASE_URL", "https://developer.zhihu.com"
    )
    ZHIHU_ACCESS_SECRET = os.getenv("ZHIHU_ACCESS_SECRET", "")
    ZHIHU_SEARCH_COUNT = min(10, max(1, int(os.getenv("ZHIHU_SEARCH_COUNT", "10"))))
    ZHIHU_HOT_LIST_LIMIT = min(
        30, max(1, int(os.getenv("ZHIHU_HOT_LIST_LIMIT", "30")))
    )

    QIANFAN_API_BASE_URL = os.getenv(
        "QIANFAN_API_BASE_URL", "https://qianfan.baidubce.com"
    )
    QIANFAN_API_KEY = os.getenv("QIANFAN_API_KEY", "")
    QIANFAN_WEB_SEARCH_PATH = os.getenv(
        "QIANFAN_WEB_SEARCH_PATH", "/v2/ai_search/web_search"
    )
    QIANFAN_TRENDING_PATH = os.getenv(
        "QIANFAN_TRENDING_PATH", "/v2/tools/baidu_trending"
    )
    QIANFAN_WEB_SEARCH_TOP_K = min(
        50, max(1, int(os.getenv("QIANFAN_WEB_SEARCH_TOP_K", "50")))
    )
    QIANFAN_REQUEST_TIMEOUT = max(
        1, int(os.getenv("QIANFAN_REQUEST_TIMEOUT", "30"))
    )

    AUTO_PUBLISH_EVENTS = (
        os.getenv("AUTO_PUBLISH_EVENTS", "false").lower() == "true"
    )
    CRAWL_DEFAULT_TARGET_COUNT = min(
        200, max(1, int(os.getenv("CRAWL_DEFAULT_TARGET_COUNT", "100")))
    )
    CRAWL_MAX_TARGET_COUNT = min(
        200, max(CRAWL_DEFAULT_TARGET_COUNT, int(os.getenv("CRAWL_MAX_TARGET_COUNT", "200")))
    )
    CRAWL_PLATFORM_PREFERRED_LIMIT = min(
        50, max(1, int(os.getenv("CRAWL_PLATFORM_PREFERRED_LIMIT", "50")))
    )
    CRAWL_REQUEST_TIMEOUT = max(1, int(os.getenv("CRAWL_REQUEST_TIMEOUT", "30")))
    CRAWL_MAX_RESPONSE_BYTES = max(
        1024, int(os.getenv("CRAWL_MAX_RESPONSE_BYTES", str(5 * 1024 * 1024)))
    )
    RSS_FEED_URL = os.getenv("RSS_FEED_URL", "")
    TASKS_RUN_SYNC = os.getenv("TASKS_RUN_SYNC", "false").lower() == "true"
    TASK_RECOVER_ON_STARTUP = (
        os.getenv("TASK_RECOVER_ON_STARTUP", "true").lower() == "true"
    )
    TASK_RUNNING_TIMEOUT_SECONDS = max(
        60, int(os.getenv("TASK_RUNNING_TIMEOUT_SECONDS", "3600"))
    )
    TASK_RECOVERY_SCAN_SECONDS = max(
        10, int(os.getenv("TASK_RECOVERY_SCAN_SECONDS", "60"))
    )
    TASK_HEARTBEAT_INTERVAL_SECONDS = max(
        5, int(os.getenv("TASK_HEARTBEAT_INTERVAL_SECONDS", "30"))
    )
    TASK_HEARTBEAT_ENABLED = (
        os.getenv("TASK_HEARTBEAT_ENABLED", "true").lower() == "true"
    )
    CRAWL_DUPLICATE_WINDOW_SECONDS = max(
        1, int(os.getenv("CRAWL_DUPLICATE_WINDOW_SECONDS", "60"))
    )
    CRAWL_RATE_LIMITED_PLATFORMS = [
        p.strip()
        for p in os.getenv("CRAWL_RATE_LIMITED_PLATFORMS", "").split(",")
        if p.strip()
    ]

    TFIDF_MAX_FEATURES = max(100, int(os.getenv("TFIDF_MAX_FEATURES", "5000")))
    TFIDF_NGRAM_MAX = min(3, max(1, int(os.getenv("TFIDF_NGRAM_MAX", "2"))))
    TFIDF_MIN_DF = max(1, int(os.getenv("TFIDF_MIN_DF", "1")))
    TFIDF_MAX_DF = min(1.0, max(0.1, float(os.getenv("TFIDF_MAX_DF", "0.90"))))
    TFIDF_SUBLINEAR_TF = os.getenv("TFIDF_SUBLINEAR_TF", "true").lower() == "true"
    TFIDF_SMOOTH_IDF = os.getenv("TFIDF_SMOOTH_IDF", "true").lower() == "true"
    TFIDF_TITLE_WEIGHT = max(0.0, float(os.getenv("TFIDF_TITLE_WEIGHT", "1.0")))
    TFIDF_BODY_WEIGHT = max(0.0, float(os.getenv("TFIDF_BODY_WEIGHT", "1.0")))
    ARTICLE_KEYWORD_LIMIT = max(1, int(os.getenv("ARTICLE_KEYWORD_LIMIT", "10")))
    EVENT_KEYWORD_LIMIT = max(1, int(os.getenv("EVENT_KEYWORD_LIMIT", "20")))
    CONTENT_ANALYSIS_MIN_NORMAL_DOCS = max(
        2, int(os.getenv("CONTENT_ANALYSIS_MIN_NORMAL_DOCS", "5"))
    )
    BGE_ENABLED = os.getenv("BGE_ENABLED", "true").lower() == "true"
    BGE_MODEL = os.getenv("BGE_MODEL", "BAAI/bge-small-zh-v1.5")
    BGE_MODEL_VERSION = os.getenv("BGE_MODEL_VERSION", "default")
    BGE_PREPROCESS_VERSION = os.getenv("BGE_PREPROCESS_VERSION", "v1")
    BGE_MAX_TEXT_LENGTH = max(100, int(os.getenv("BGE_MAX_TEXT_LENGTH", "2000")))

    LLM_API_KEY = os.getenv("LLM_API_KEY", "")
    LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
    LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "deepseek-chat")
    LLM_REQUEST_TIMEOUT = max(1, int(os.getenv("LLM_REQUEST_TIMEOUT", "30")))
    RISK_LLM_MIN_SCORE = min(
        100.0, max(0.0, float(os.getenv("RISK_LLM_MIN_SCORE", "30")))
    )
    RISK_LLM_MAX_SCORE = min(
        100.0, max(RISK_LLM_MIN_SCORE, float(os.getenv("RISK_LLM_MAX_SCORE", "70")))
    )
    LLM_KEYWORD_BATCH_SIZE = min(
        20, max(1, int(os.getenv("LLM_KEYWORD_BATCH_SIZE", "5")))
    )

    SENTIMENT_ALGORITHM_VERSION = os.getenv(
        "SENTIMENT_ALGORITHM_VERSION", "sentiment-v1"
    )
    SENTIMENT_PROMPT_VERSION = os.getenv(
        "SENTIMENT_PROMPT_VERSION", "sentiment-prompt-v1"
    )
    SENTIMENT_PREPROCESS_VERSION = os.getenv(
        "SENTIMENT_PREPROCESS_VERSION", "sentiment-text-v1"
    )
    SENTIMENT_TEXT_LIMIT = max(1, int(os.getenv("SENTIMENT_TEXT_LIMIT", "500")))
    SENTIMENT_LLM_MAX_CONCURRENCY = max(
        1, int(os.getenv("SENTIMENT_LLM_MAX_CONCURRENCY", "3"))
    )
    SENTIMENT_LLM_RETRY_COUNT = max(
        0, int(os.getenv("SENTIMENT_LLM_RETRY_COUNT", "3"))
    )
    SENTIMENT_NEUTRAL_SCORE_MIN = float(
        os.getenv("SENTIMENT_NEUTRAL_SCORE_MIN", "-0.20")
    )
    SENTIMENT_NEUTRAL_SCORE_MAX = float(
        os.getenv("SENTIMENT_NEUTRAL_SCORE_MAX", "0.20")
    )
    SENTIMENT_MIN_SUCCESS_RATIO = min(
        1.0, max(0.01, float(os.getenv("SENTIMENT_MIN_SUCCESS_RATIO", "0.80")))
    )
    SENTIMENT_PLATFORM_MIN_ARTICLES = max(
        1, int(os.getenv("SENTIMENT_PLATFORM_MIN_ARTICLES", "3"))
    )
    SENTIMENT_PLATFORM_MIN_REPRESENTATIVES = max(
        1, int(os.getenv("SENTIMENT_PLATFORM_MIN_REPRESENTATIVES", "2"))
    )
    SNOWNLP_POSITIVE_THRESHOLD = float(
        os.getenv("SNOWNLP_POSITIVE_THRESHOLD", "0.60")
    )
    SNOWNLP_NEGATIVE_THRESHOLD = float(
        os.getenv("SNOWNLP_NEGATIVE_THRESHOLD", "0.40")
    )
    SNOWNLP_CONFIDENCE_CAP = min(
        1.0, max(0.0, float(os.getenv("SNOWNLP_CONFIDENCE_CAP", "0.75")))
    )

    HOTSPOT_WINDOW_DAYS = max(1, int(os.getenv("HOTSPOT_WINDOW_DAYS", "7")))
    HOTSPOT_TOP_LIMIT = max(1, int(os.getenv("HOTSPOT_TOP_LIMIT", "20")))
    HOTSPOT_MIN_REPORTS = max(1, int(os.getenv("HOTSPOT_MIN_REPORTS", "3")))
    HOTSPOT_MIN_PLATFORMS = max(1, int(os.getenv("HOTSPOT_MIN_PLATFORMS", "2")))
    HOTSPOT_RECENT_ACTIVITY_HOURS = max(
        1, int(os.getenv("HOTSPOT_RECENT_ACTIVITY_HOURS", "24"))
    )
    HOTSPOT_EXPANSION_SEED_LIMIT = max(
        1, int(os.getenv("HOTSPOT_EXPANSION_SEED_LIMIT", "20"))
    )
    HOTSPOT_EXPANSION_TARGET_PER_SEED = max(
        1, int(os.getenv("HOTSPOT_EXPANSION_TARGET_PER_SEED", "20"))
    )
    LDA_MAX_TOPICS = max(2, int(os.getenv("LDA_MAX_TOPICS", "12")))
    LDA_TOP_WORDS = max(1, int(os.getenv("LDA_TOP_WORDS", "20")))
    LDA_RANDOM_STATE = int(os.getenv("LDA_RANDOM_STATE", "42"))
    LDA_MAX_ITER = max(1, int(os.getenv("LDA_MAX_ITER", "100")))
    LDA_TOPIC_DIVERSITY_MIN = min(
        1.0, max(0.0, float(os.getenv("LDA_TOPIC_DIVERSITY_MIN", "0.70")))
    )
    LDA_SMALL_TOPIC_RATIO_MAX = min(
        1.0, max(0.0, float(os.getenv("LDA_SMALL_TOPIC_RATIO_MAX", "0.20")))
    )
    LDA_LOW_CONFIDENCE_THRESHOLD = min(
        1.0,
        max(0.0, float(os.getenv("LDA_LOW_CONFIDENCE_THRESHOLD", "0.45"))),
    )
    HEAT_CORE_WEIGHT = min(
        1.0, max(0.0, float(os.getenv("HEAT_CORE_WEIGHT", "0.70")))
    )
    HEAT_SPREAD_WEIGHT = min(
        1.0, max(0.0, float(os.getenv("HEAT_SPREAD_WEIGHT", "0.30")))
    )
    HEAT_HALF_LIFE_HOURS = max(
        1, int(os.getenv("HEAT_HALF_LIFE_HOURS", "24"))
    )
    HEAT_FORMULA_VERSION = os.getenv("HEAT_FORMULA_VERSION", "v1")

    DAILY_HOT_SCHEDULER_ENABLED = (
        os.getenv("DAILY_HOT_SCHEDULER_ENABLED", "false").lower() == "true"
    )
    DAILY_HOT_SOURCES = [
        source.strip().casefold()
        for source in os.getenv(
            "DAILY_HOT_SOURCES",
            "weibo_hot,baidu_hot,zhihu_hot",
        ).split(",")
        if source.strip()
    ]
    DAILY_HOT_SOURCE_LIMIT = min(
        100,
        max(1, int(os.getenv("DAILY_HOT_SOURCE_LIMIT", "30"))),
    )
    DAILY_HOT_RESULT_LIMIT = min(
        100,
        max(1, int(os.getenv("DAILY_HOT_RESULT_LIMIT", "10"))),
    )
    DAILY_HOT_RRF_K = max(1, int(os.getenv("DAILY_HOT_RRF_K", "60")))
    DAILY_HOT_TTL_SECONDS = max(
        60,
        int(os.getenv("DAILY_HOT_TTL_SECONDS", "900")),
    )
    DAILY_HOT_REFRESH_INTERVAL_SECONDS = max(
        60,
        int(os.getenv("DAILY_HOT_REFRESH_INTERVAL_SECONDS", "900")),
    )
    DAILY_HOT_SYSTEM_USERNAME = os.getenv(
        "DAILY_HOT_SYSTEM_USERNAME",
        DEMO_ADMIN_USERNAME,
    ).strip()
    DAILY_HOT_ENRICH_TARGET_COUNT = min(
        100,
        max(1, int(os.getenv("DAILY_HOT_ENRICH_TARGET_COUNT", "20"))),
    )

    EVENT_AGGREGATION_ATTACH_THRESHOLD = min(
        1.0,
        max(0.0, float(os.getenv("EVENT_AGGREGATION_ATTACH_THRESHOLD", "0.50"))),
    )
    EVENT_AGGREGATION_CREATE_THRESHOLD = min(
        1.0,
        max(0.0, float(os.getenv("EVENT_AGGREGATION_CREATE_THRESHOLD", "0.40"))),
    )
    EVENT_AGGREGATION_MOVE_MARGIN = min(
        1.0, max(0.0, float(os.getenv("EVENT_AGGREGATION_MOVE_MARGIN", "0.10")))
    )
    EVENT_AGGREGATION_BGE_WEIGHT = max(
        0.0, float(os.getenv("EVENT_AGGREGATION_BGE_WEIGHT", "0.55"))
    )
    EVENT_AGGREGATION_TFIDF_WEIGHT = max(
        0.0, float(os.getenv("EVENT_AGGREGATION_TFIDF_WEIGHT", "0.20"))
    )
    EVENT_AGGREGATION_ENTITY_WEIGHT = max(
        0.0, float(os.getenv("EVENT_AGGREGATION_ENTITY_WEIGHT", "0.15"))
    )
    EVENT_AGGREGATION_TIME_WEIGHT = max(
        0.0, float(os.getenv("EVENT_AGGREGATION_TIME_WEIGHT", "0.10"))
    )
    EVENT_AGGREGATION_CANDIDATE_LIMIT = max(
        1, int(os.getenv("EVENT_AGGREGATION_CANDIDATE_LIMIT", "20"))
    )
    EVENT_AGGREGATION_MIN_EVIDENCE = max(
        1, int(os.getenv("EVENT_AGGREGATION_MIN_EVIDENCE", "3"))
    )
    EVENT_AGGREGATION_MIN_CLUSTER_SIZE = max(
        1, int(os.getenv("EVENT_AGGREGATION_MIN_CLUSTER_SIZE", "2"))
    )
    EVENT_AGGREGATION_ALGORITHM_VERSION = os.getenv(
        "EVENT_AGGREGATION_ALGORITHM_VERSION", "event-aggregation-v1"
    )
    EVENT_SEARCH_CACHE_HOURS = max(
        1, int(os.getenv("EVENT_SEARCH_CACHE_HOURS", "2"))
    )
    EVENT_RELATED_LIMIT = max(1, int(os.getenv("EVENT_RELATED_LIMIT", "5")))
