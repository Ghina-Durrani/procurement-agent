
import pytest

from app.db.session import check_connection


@pytest.mark.integration
def test_database_connection_works():
    assert check_connection() is True
