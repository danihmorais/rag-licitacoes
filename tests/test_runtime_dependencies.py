from importlib.metadata import version


def test_gpu_requirements_are_canonical():
    from pathlib import Path

    requirements = Path(__file__).parents[1] / "requirements.txt"
    text = requirements.read_text(encoding="utf-8")
    lines = {line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")}
    assert "fastembed-gpu==0.8.0" in lines
    assert "fastembed==0.8.0" not in lines
    assert not any(line.startswith("onnxruntime==") for line in lines)

def test_gpu_requirements_do_not_mix_cpu_fastembed_stack():
    from pathlib import Path

    requirements = Path(__file__).parents[1] / "requirements-gpu.txt"
    text = requirements.read_text(encoding="utf-8")
    lines = {line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")}
    assert "fastembed-gpu==0.8.0" in lines
    assert "fastembed==0.8.0" not in lines
    assert not any(line.startswith("onnxruntime==") for line in lines)
