import sys
from pathlib import Path
from sqlalchemy import create_engine, inspect, text

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
def _database_url(database_url):
    prefix='sqlite:///'
    if database_url.startswith(prefix):
        value=database_url[len(prefix):]
        if value and not Path(value).is_absolute():
            return prefix + str((BACKEND_ROOT/'instance'/value).resolve()).replace('\\','/')
    return database_url

def run_migration(database_url):
    database_url=_database_url(database_url)
    engine=create_engine(database_url)
    try:
        if not inspect(engine).has_table('user') or 'status' in {c['name'] for c in inspect(engine).get_columns('user')}: return
        ddl='ALTER TABLE user ADD COLUMN status INTEGER NOT NULL DEFAULT 1' if engine.dialect.name!='mysql' else 'ALTER TABLE user ADD COLUMN status TINYINT NOT NULL DEFAULT 1'
        with engine.begin() as c: c.execute(text(ddl))
    finally: engine.dispose()

if __name__ == '__main__':
    from app.core.config import Config
    run_migration(Config.SQLALCHEMY_DATABASE_URI)
