import asyncio
from logging.config import fileConfig

import alembic_postgresql_enum  # noqa: F401
from alembic.script import write_hooks
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = None


@write_hooks.register("import_sqlmodel")
def add_import_sqlmodel(filename, options):
    with open(filename, "r") as fp:
        lines = list(fp)
    lines.insert(7, "import sqlmodel.sql.sqltypes\n")
    with open(filename, "w") as fp:
        fp.writelines(lines)


def set_target_metadata():
    global target_metadata
    from sqlmodel import SQLModel

    from src.models import (
        chart,  # noqa: F401
        daily_report,  # noqa: F401
        optimize,  # noqa: F401
        plan,  # noqa: F401
        progress,  # noqa: F401
        project,  # noqa: F401
        resource,  # noqa: F401
        resource_public,  # noqa: F401
        resource_reuse_config,  # noqa: F401
        resource_usage,  # noqa: F401
        tag,  # noqa: F401
        task,  # noqa: F401
        weather,  # noqa: F401
    )

    target_metadata = SQLModel.metadata


set_target_metadata()

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well. By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    from src.config import settings

    # settings.database_async_url：postgresql:// 运维写法 → asyncpg 驱动 URL
    url = settings.database_async_url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    from src.config import settings

    connectable = async_engine_from_config(
        {"url": settings.database_async_url},
        prefix="",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
