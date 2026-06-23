from datetime import datetime, timezone

from peewee import Model, UUIDField, CharField, DateTimeField, TextField, ForeignKeyField, Proxy

database_proxy = Proxy()


class StoredGame(Model):
    uuid = UUIDField(primary_key=True)
    name = CharField()
    deck = CharField()
    last_active = DateTimeField(default=lambda: datetime.now(timezone.utc))

    class Meta:
        database = database_proxy


class HistoryEntry(Model):
    game = ForeignKeyField(StoredGame, backref='history_entries')
    deck = CharField()
    recorded_at = DateTimeField(default=lambda: datetime.now(timezone.utc))
    results = TextField()
    """JSON-encoded list of player snapshots, same shape as Player.state_with_hand()."""

    class Meta:
        database = database_proxy


def ensure_schema() -> None:
    """Adds columns introduced after the initial release to pre-existing database files."""
    StoredGame.create_table()
    HistoryEntry.create_table()
    columns = {column.name for column in database_proxy.get_columns(StoredGame._meta.table_name)}
    if 'last_active' not in columns:
        database_proxy.execute_sql(f'ALTER TABLE {StoredGame._meta.table_name} ADD COLUMN last_active DATETIME')
        StoredGame.update(last_active=datetime.now(timezone.utc)).where(StoredGame.last_active.is_null()).execute()

