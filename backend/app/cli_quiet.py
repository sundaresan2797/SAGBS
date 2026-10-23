"""Keep the command-line tools readable: with DEBUG=true the application logs every database query, which would bury
the few lines a person needs to read."""

import logging

from app.database.session import engine


def quiet() -> None:
    logging.getLogger().setLevel(logging.WARNING)
    for name in ("sqlalchemy", "sqlalchemy.engine", "sqlalchemy.engine.Engine", "asyncio", "ems.requests"):
        logging.getLogger(name).setLevel(logging.WARNING)
    engine.sync_engine.echo = False
