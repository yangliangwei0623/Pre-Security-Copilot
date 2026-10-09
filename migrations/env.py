from alembic import context

config = context.config
connection = config.attributes.get("connection")
if connection is None:
    from sqlalchemy import create_engine
    from app.config import Settings
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    connection = create_engine(settings.database_url).connect()
context.configure(connection=connection, target_metadata=None)
with context.begin_transaction():
    context.run_migrations()
