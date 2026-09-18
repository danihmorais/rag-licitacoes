from importlib.metadata import version


def test_onnxruntime_is_pinned_before_external_data_path_change():
    raw = version("onnxruntime").split(".")
    parsed = tuple(int(part.split("+")[0]) for part in raw[:3])
    assert parsed == (1, 23, 2)


def test_gpu_requirements_do_not_mix_cpu_fastembed_stack():
    from pathlib import Path

    requirements = Path(__file__).parents[1] / "requirements-gpu.txt"
    text = requirements.read_text(encoding="utf-8")
    lines = {line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")}
    assert "fastembed-gpu==0.8.0" in lines
    assert "fastembed==0.8.0" not in lines
    assert not any(line.startswith("onnxruntime==") for line in lines)
