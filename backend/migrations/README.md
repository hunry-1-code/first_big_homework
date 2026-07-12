# Database Migrations

`db.create_all()` only creates missing tables and does not alter existing columns. For a database created from the original project skeleton, back it up and run the dated SQL migration once before starting the new crawler/preprocessing code.

```powershell
python migrations\migrate_crawler_preprocessing.py
```

The Python runner is required because it imports the same `normalize_url` implementation used at runtime before it fills `article.url_hash` and creates the unique index. Do not execute the SQL file directly.

Stop the backend before running the migration. The runner validates every legacy URL before any MySQL DDL is executed. If multiple old rows normalize to the same URL, it aborts without altering the schema and reports the conflicting article IDs; merge or remove those duplicate rows, then run it again.

Fresh development databases do not need this script because the current SQLAlchemy metadata creates the complete schema. The migration targets MySQL 8 and the original skeleton schema; review index/constraint names if the database was changed manually.

After the crawler/preprocessing migration, add the content-analysis tables with:

```powershell
python migrations\migrate_content_analysis.py
```

This creates `analysis_run`, `analysis_run_article`, and `article_embedding`. It does not modify or copy article content and is safe to rerun because the SQL uses `CREATE TABLE IF NOT EXISTS`.

After content analysis, add hotspot topic and heat persistence with:

```powershell
python migrations\migrate_hotspot_discovery.py
```

This creates `hotspot_run`, `hot_seed_expansion`, `topic_result`, `topic_article_assignment`, and `event_heat_snapshot`, then adds current hotspot summary columns and the snapshot foreign key to `event`. MySQL DDL commits each statement independently, so an interrupted run can leave a partially applied migration; rerun the Python runner, which skips existing event columns and the existing named foreign key.
