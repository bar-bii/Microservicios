from presentation.access_log import AccessLogMiddleware
from presentation.main import app


def test_main_installs_access_log_middleware():
    assert any(middleware.cls is AccessLogMiddleware for middleware in app.user_middleware)
