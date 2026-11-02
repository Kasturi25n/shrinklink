from app.config import Settings


def test_heroku_style_postgres_url_is_normalised():
    s = Settings(database_url="postgres://u:p@host:5432/db")
    assert s.database_url == "postgresql://u:p@host:5432/db"


def test_other_database_urls_untouched():
    assert Settings(database_url="sqlite:///x.db").database_url == "sqlite:///x.db"
    url = "postgresql+psycopg2://u:p@host/db"
    assert Settings(database_url=url).database_url == url


def test_base_url_falls_back_to_render_external_url(monkeypatch):
    monkeypatch.delenv("BASE_URL", raising=False)
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://my-app.onrender.com")
    assert Settings().base_url == "https://my-app.onrender.com"


def test_explicit_base_url_beats_render_url(monkeypatch):
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://my-app.onrender.com")
    monkeypatch.setenv("BASE_URL", "https://sho.rt")
    assert Settings().base_url == "https://sho.rt"
