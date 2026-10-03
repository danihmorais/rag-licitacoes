def test_gpu_requirements_are_canonical():
    from pathlib import Path

    requirements = Path(__file__).parents[1] / "requirements.txt"
    text = requirements.read_text(encoding="utf-8")
    lines = {line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")}
    assert "fastembed-gpu==0.8.0" in lines
    assert "fastembed==0.8.0" not in lines
    assert "onnxruntime-gpu==1.23.2" in lines
    assert not any(line.startswith("onnxruntime==") for line in lines)
    assert "nvidia-cuda-runtime-cu12==12.9.79" in lines
    assert "nvidia-cublas-cu12==12.9.2.10" in lines
    assert "nvidia-cudnn-cu12==9.27.0.42" in lines
    assert "nvidia-cufft-cu12==11.4.1.4" in lines
    assert "PyMuPDF==1.28.2" in lines
    assert "pytesseract==0.3.13" in lines
    assert any(line.startswith("Pillow") for line in lines)

def test_gpu_requirements_do_not_mix_cpu_fastembed_stack():
    from pathlib import Path

    requirements = Path(__file__).parents[1] / "requirements.txt"
    text = requirements.read_text(encoding="utf-8")
    lines = {line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")}
    assert "fastembed-gpu==0.8.0" in lines
    assert "fastembed==0.8.0" not in lines
    assert "onnxruntime-gpu==1.23.2" in lines
    assert not any(line.startswith("onnxruntime==") for line in lines)

def test_gpu_runtime_validation_preloads_cuda_dlls(monkeypatch):
    import config

    monkeypatch.setattr(config, "FASTEMBED_REQUIRE_CUDA", True)
    monkeypatch.setattr(config, "FASTEMBED_PROVIDERS", ("CUDAExecutionProvider",))

    class FakeOrt:
        called = False

        @staticmethod
        def get_available_providers():
            return ["CUDAExecutionProvider", "CPUExecutionProvider"]

        @classmethod
        def preload_dlls(cls, directory=""):
            cls.called = True
            assert directory == ""

    monkeypatch.setitem(__import__("sys").modules, "onnxruntime", FakeOrt)
    config.validate_gpu_runtime()
    assert FakeOrt.called
