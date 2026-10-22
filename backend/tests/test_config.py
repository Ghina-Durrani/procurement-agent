import pytest
from app.config import Settings


def test_database_url_handles_special_characters():
    settings = Settings(
        _env_file=None,
        postgres_password="p@ss:w/rd#1",
    )

    url = settings.build_database_url()

    rendered_url = url.render_as_string(hide_password=False)

    assert "p%40ss%3Aw%2Frd%231" in rendered_url
    assert "p@ss:w/rd#1" not in rendered_url


def test_missing_password_raises_error():
    settings = Settings(
        _env_file=None,
        postgres_password=None,
    )

    with pytest.raises(RuntimeError, match="POSTGRES_PASSWORD is not set"):
        settings.build_database_url()