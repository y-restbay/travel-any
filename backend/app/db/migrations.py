from sqlalchemy import text
from sqlalchemy.engine import Engine


def run_lightweight_migrations(engine: Engine) -> None:
    """Tiny SQLite-friendly migrations for the V1 local prototype."""
    with engine.begin() as connection:
        if engine.dialect.name == "sqlite":
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS embedding_configs (
                        id INTEGER NOT NULL PRIMARY KEY,
                        provider VARCHAR(80) DEFAULT 'hash' NOT NULL,
                        model_name VARCHAR(160) DEFAULT 'hash-384' NOT NULL,
                        api_key TEXT DEFAULT '' NOT NULL,
                        base_url VARCHAR(500) DEFAULT '' NOT NULL,
                        is_active BOOLEAN DEFAULT 1 NOT NULL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
                    )
                    """
                )
            )
            connection.execute(
                text("CREATE INDEX IF NOT EXISTS ix_embedding_configs_id ON embedding_configs (id)")
            )
            connection.execute(
                text("CREATE INDEX IF NOT EXISTS ix_embedding_configs_provider ON embedding_configs (provider)")
            )
            connection.execute(
                text("CREATE INDEX IF NOT EXISTS ix_embedding_configs_is_active ON embedding_configs (is_active)")
            )

            columns = connection.execute(text("PRAGMA table_info(system_prompts)")).mappings().all()
            names = {str(column["name"]) for column in columns}
            if columns and "knowledge_scope" not in names:
                connection.execute(
                    text("ALTER TABLE system_prompts ADD COLUMN knowledge_scope TEXT NOT NULL DEFAULT '[]'")
                )

            llm_columns = connection.execute(text("PRAGMA table_info(llm_configs)")).mappings().all()
            llm_names = {str(column["name"]) for column in llm_columns}
            if llm_columns and "runtime" not in llm_names:
                connection.execute(
                    text("ALTER TABLE llm_configs ADD COLUMN runtime VARCHAR(20) NOT NULL DEFAULT 'tools'")
                )
