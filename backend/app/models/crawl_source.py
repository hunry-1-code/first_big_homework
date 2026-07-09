from app.extensions import db


class CrawlSource(db.Model):
    __tablename__ = "crawl_source"

    id = db.Column(db.Integer, primary_key=True)
    platform = db.Column(db.String(50), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    keywords = db.Column(db.JSON)
    frequency = db.Column(db.Integer, default=30)
    last_crawl_at = db.Column(db.DateTime)
    enabled = db.Column(db.Boolean, default=True)

