from jurisprudencia.batch import collect_batch
from jurisprudencia.schema import JurisprudenciaRecord


def test_collect_batch_treats_limit_as_total_per_tribunal(monkeypatch, tmp_path):
    calls = []
    counters = {"tcu": 0, "stj": 0}

    def fake_collect(tribunals, query, limit, **kwargs):
        tribunal = tribunals[0]
        calls.append((tribunal, query, limit))
        start = counters[tribunal]
        count = min(limit, 8 - start)
        counters[tribunal] += count
        return [
            JurisprudenciaRecord(
                tribunal=tribunal.upper(),
                numero_processo=f"{tribunal}-{index}",
                ementa=f"Licitação administrativa {index}.",
                url_oficial=f"https://example.test/{tribunal}/{index}",
            )
            for index in range(start, start + count)
        ]

    monkeypatch.setattr("jurisprudencia.batch.collect", fake_collect)
    monkeypatch.setattr("jurisprudencia.batch.save_record", lambda record, output_dir: None)

    records = collect_batch(
        ("tcu", "stj"),
        ("consulta 1", "consulta 2", "consulta 3", "consulta 4"),
        8,
        per_query_limit=3,
        output_dir=tmp_path,
        strict=True,
        min_records_per_tribunal=8,
        include_sumulas=False,
    )

    assert len(records) == 16
    assert len([record for record in records if record.tribunal == "TCU"]) == 8
    assert len([record for record in records if record.tribunal == "STJ"]) == 8
    assert all(limit <= 3 for _, _, limit in calls)
    assert [limit for tribunal, _, limit in calls if tribunal == "tcu"] == [3, 3, 2]
    assert [limit for tribunal, _, limit in calls if tribunal == "stj"] == [3, 3, 2]


def test_collect_batch_strict_enforces_minimum_per_tribunal(monkeypatch, tmp_path):
    def fake_collect(tribunals, query, limit, **kwargs):
        tribunal = tribunals[0]
        return [
            JurisprudenciaRecord(
                tribunal=tribunal.upper(),
                numero_processo=f"{tribunal}-1",
                ementa="Licitação administrativa.",
                url_oficial=f"https://example.test/{tribunal}/1",
            )
        ]

    monkeypatch.setattr("jurisprudencia.batch.collect", fake_collect)
    monkeypatch.setattr("jurisprudencia.batch.save_record", lambda record, output_dir: None)

    try:
        collect_batch(
            ("tcu", "stj"),
            ("consulta 1",),
            10,
            per_query_limit=10,
            output_dir=tmp_path,
            strict=True,
            min_records_per_tribunal=2,
            include_sumulas=False,
        )
    except RuntimeError as exc:
        assert "tcu=1" in str(exc)
        assert "stj=1" in str(exc)
    else:
        raise AssertionError("a coleta estrita deveria falhar abaixo do mínimo por tribunal")


def test_collect_batch_does_not_fetch_unrequested_sumula_tribunals(monkeypatch, tmp_path):
    calls = []

    def fake_collect(tribunals, query, limit, **kwargs):
        return [
            JurisprudenciaRecord(
                tribunal=tribunals[0].upper(),
                numero_processo="stj-1",
                ementa="Licitação administrativa.",
                url_oficial="https://example.test/stj/1",
            )
        ]

    def fake_sumulas(**kwargs):
        calls.append(kwargs)
        raise AssertionError("TCU/TCESP não deveriam ser coletados")

    monkeypatch.setattr("jurisprudencia.batch.collect", fake_collect)
    monkeypatch.setattr("jurisprudencia.batch.collect_sumulas", fake_sumulas)

    records = collect_batch(
        ("stj",),
        ("licitação",),
        1,
        output_dir=tmp_path,
        strict=True,
        min_records_per_tribunal=1,
        include_sumulas=True,
    )

    assert len(records) == 1
    assert calls == []
