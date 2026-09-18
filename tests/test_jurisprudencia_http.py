from jurisprudencia.collector import JitterRetry, RotatingSession


def test_retry_backoff_includes_jitter(monkeypatch):
    retry = JitterRetry(total=2, backoff_factor=1.0, status_forcelist=(500,))
    monkeypatch.setattr("jurisprudencia.collector.random.uniform", lambda a, b: b)
    retry = retry.increment(method="GET", url="https://example.test", response=type("Response", (), {"status": 500, "get_redirect_location": lambda self: None})())
    assert retry.get_backoff_time() > 0


def test_session_rotates_user_agent(monkeypatch):
    session = RotatingSession()
    session._user_agents = iter(["ua-one", "ua-two"])
    values = []

    def fake_request(*args, **kwargs):
        values.append(kwargs["headers"]["User-Agent"])
        return object()

    monkeypatch.setattr("requests.Session.request", fake_request)
    session.request("GET", "https://example.test")
    session.request("GET", "https://example.test")
    assert values == ["ua-one", "ua-two"]
