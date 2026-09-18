from importlib.metadata import version


def test_onnxruntime_is_pinned_before_external_data_path_change():
    raw = version("onnxruntime").split(".")
    parsed = tuple(int(part.split("+")[0]) for part in raw[:3])
    assert parsed == (1, 23, 2)
