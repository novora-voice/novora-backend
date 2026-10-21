from logging.config import fileConfig
import os
from pathlib import Path

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

backend_root = Path(__file__).resolve().parents[1]
load_dotenv(backend_root / ".env")
database_url = os.environ.get("NOVORA_DATABASE_URL")
if not database_url:
    raise RuntimeError("NOVORA_DATABASE_URL must be set before running Alembic.")

# auth_utils defines the authentication ORM models alongside application startup
# settings. Supply a migration-only key if the runtime secret is not configured.
os.environ.setdefault("NOVORA_JWT_SECRET", "alembic-metadata-import-only")
os.environ.setdefault("NOVORA_DATABASE_URL", database_url)

from novora.adapters.db_models import Base as ApplicationBase  # noqa: E402
from novora.api.auth_utils import Base as AuthBase  # noqa: E402

target_metadata = [ApplicationBase.metadata, AuthBase.metadata]


def run_migrations_offline() -> None:
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
