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
    assert "nvidia-cuda-nvrtc-cu12==12.9.86" in lines
    assert "nvidia-curand-cu12==10.3.10.19" in lines
    assert "nvidia-nvjitlink-cu12==12.9.86" in lines
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


def test_cuda_preload_uses_installed_distribution_locations(monkeypatch, tmp_path):
    import config

    class FakePackage:
        def __init__(self, root):
            self.root = root

        def locate_file(self, relative):
            return self.root / relative

    packages = {}
    for name, relatives in (
        ('nvidia-cublas-cu12', (
            'nvidia/cublas/lib/libcublasLt.so.12',
            'nvidia/cublas/lib/libcublas.so.12',
        )),
        ('nvidia-cuda-runtime-cu12', (
            'nvidia/cuda_runtime/lib/libcudart.so.12',
        )),
    ):
        for relative in relatives:
            path = tmp_path / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
        packages[name] = FakePackage(tmp_path)

    loaded = []
    class FakeCtypes:
        RTLD_GLOBAL = 0

        @staticmethod
        def CDLL(path, mode=0):
            loaded.append((path, mode))
            return object()

    class FakeMetadata:
        class PackageNotFoundError(Exception):
            pass

        @staticmethod
        def distribution(name):
            try:
                return packages[name]
            except KeyError as exc:
                raise FakeMetadata.PackageNotFoundError(name) from exc

    monkeypatch.setattr(config.os, 'name', 'posix', raising=False)
    monkeypatch.setitem(__import__('sys').modules, 'ctypes', FakeCtypes)
    monkeypatch.setitem(__import__('sys').modules, 'importlib.metadata', FakeMetadata)
    config._preload_nvidia_cuda_libraries()
    assert any(path.endswith('libcublasLt.so.12') for path, _ in loaded)
    assert any(path.endswith('libcudart.so.12') for path, _ in loaded)
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

    monkeypatch.setattr(config, "_preload_nvidia_cuda_libraries", lambda: None)
    monkeypatch.setitem(__import__("sys").modules, "onnxruntime", FakeOrt)
    config.validate_gpu_runtime()
    assert FakeOrt.called


def test_ci_requirements_use_cpu_fastembed_stack():
    from pathlib import Path

    path = Path(__file__).parents[1] / "requirements-ci.txt"
    lines = {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.lstrip().startswith("#")}
    assert "fastembed==0.8.0" in lines
    assert "fastembed-gpu==0.8.0" not in lines
    assert "onnxruntime==1.23.2" in lines
    assert not any(line.startswith("onnxruntime-gpu==") for line in lines)
    assert not any(line.startswith("nvidia-") for line in lines)
