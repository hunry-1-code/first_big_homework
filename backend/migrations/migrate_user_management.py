from sqlalchemy import create_engine, inspect, text
def run_migration(database_url):
    engine=create_engine(database_url)
    try:
        if not inspect(engine).has_table('user') or 'status' in {c['name'] for c in inspect(engine).get_columns('user')}: return
        ddl='ALTER TABLE user ADD COLUMN status INTEGER NOT NULL DEFAULT 1' if engine.dialect.name!='mysql' else 'ALTER TABLE user ADD COLUMN status TINYINT NOT NULL DEFAULT 1'
        with engine.begin() as c: c.execute(text(ddl))
    finally: engine.dispose()
