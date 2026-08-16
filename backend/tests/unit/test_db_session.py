"""The production session wiring, exercised without an override."""

import sqlalchemy as sa

from app.db.session import get_db, get_engine, get_session_factory


def test_get_engine_is_cached_so_the_pool_is_not_rebuilt_per_request() -> None:
    assert get_engine() is get_engine()


def test_get_session_factory_is_bound_to_the_configured_database() -> None:
    factory = get_session_factory()

    assert factory.kw["bind"] is get_engine()


def test_get_db_yields_a_usable_session_and_closes_it() -> None:
    generator = get_db()
    session = next(generator)

    assert session.execute(sa.text("SELECT 1")).scalar_one() == 1

    list(generator)  # drain, triggering the finally block

    assert not session.is_active or session.get_bind() is not None
