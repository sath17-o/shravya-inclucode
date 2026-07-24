from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import wave
from contextlib import nullcontext
from pathlib import Path

import pytest


@pytest.fixture
def runner_module():
    path = Path(__file__).resolve().parents[2] / "scripts" / "indicconformer_runner.py"
    spec = importlib.util.spec_from_file_location("indicconformer_runner_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeTensor:
    def unsqueeze(self, _dimension):
        return self

    def __truediv__(self, _value):
        return self


class FakeTorch:
    float32 = object()

    def __init__(self) -> None:
        self.samples = ()

    def tensor(self, samples, *, dtype):
        assert dtype is self.float32
        self.samples = samples
        return FakeTensor()

    @staticmethod
    def no_grad():
        return nullcontext()


class CallableIndicConformer:
    def __init__(self, result: object = "സസ്യങ്ങൾക്ക് ജലം ആവശ്യമാണ്.") -> None:
        self.result = result
        self.calls: list[tuple[object, str, str]] = []

    def __call__(self, waveform, language, decoder):
        self.calls.append((waveform, language, decoder))
        return self.result


class TranscribeOnlyModel:
    def transcribe(self, *_args, **_kwargs):
        return "must not be used"


class RuntimeTorch:
    __version__ = "test-torch"


def _wav(path: Path, frame_count: int = 16000) -> None:
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(b"\x00\x00" * frame_count)


def _request(path: Path, model: Path) -> dict[str, object]:
    return {
        "schema_version": 1,
        "request_id": "00000000-0000-0000-0000-000000000001",
        "audio": {
            "path": str(path.resolve()),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "duration_ms": 1000,
        },
        "model": {
            "local_path": str(model.resolve()),
            "expected_model_id": "ai4bharat/indic-conformer-600m-multilingual",
            "expected_revision": "e9b71b369c048e2c6b634d4c131061c34e441179",
            "language": "ml",
            "decoder": "ctc",
            "offline_only": True,
        },
        "segments": [{"sequence": 1, "start_ms": 0, "end_ms": 1000}],
    }


def _model_module(model_path: Path, source: str | None = None) -> Path:
    path = model_path / "model_onnx.py"
    path.write_text(
        source
        or """
class IndicASRConfig:
    def __init__(self, *, ts_folder):
        self.ts_folder = ts_folder

class IndicASRModel:
    def __init__(self, config):
        self.config = config
        self.eval_called = False

    def eval(self):
        self.eval_called = True

    def __call__(self, waveform, language, decoder):
        return "മലയാളം"
""",
        encoding="utf-8",
    )
    return path


def _load_local_model(runner_module, monkeypatch, model_path: Path):
    monkeypatch.setitem(sys.modules, "torch", RuntimeTorch())
    return runner_module._lazy_model(model_path)


def test_runner_validates_strict_offline_request_and_wav(tmp_path: Path, runner_module) -> None:
    audio = tmp_path / "audio.wav"
    model = tmp_path / "model"
    model.mkdir()
    _wav(audio)
    request = runner_module.validate_request(_request(audio, model))
    frames, count = runner_module.validate_wav(request["audio"], request["segments"])

    assert count == 16000
    assert len(frames) == 32000


def test_runner_uses_callable_indicconformer_contract(runner_module) -> None:
    torch = FakeTorch()
    model = CallableIndicConformer()

    text = runner_module._model_text(model, torch, b"\x00\x00" * 16, 16, 0, 1)

    assert text == "സസ്യങ്ങൾക്ക് ജലം ആവശ്യമാണ്."
    assert len(model.calls) == 1
    assert model.calls[0][1:] == ("ml", "ctc")
    assert len(torch.samples) == 16


@pytest.mark.parametrize("result", ["", "\ufffd unsafe"])
def test_runner_rejects_empty_or_unsafe_callable_output(runner_module, result: str) -> None:
    with pytest.raises(runner_module.RunnerError):
        runner_module._model_text(CallableIndicConformer(result), FakeTorch(), b"\x00\x00", 1, 0, 1)


def test_runner_rejects_transcribe_only_model(runner_module) -> None:
    with pytest.raises(runner_module.RunnerError, match="hybrid_model_contract_invalid"):
        runner_module._model_text(TranscribeOnlyModel(), FakeTorch(), b"\x00\x00", 1, 0, 1)


def test_runner_clamps_only_final_rounding_samples(runner_module) -> None:
    # 15,992 samples round to 1,000 ms even though 1,000 ms maps to 16,000 samples.
    torch = FakeTorch()
    model = CallableIndicConformer()
    text = runner_module._model_text(model, torch, b"\x00\x00" * 15992, 15992, 0, 1000)

    assert text == "സസ്യങ്ങൾക്ക് ജലം ആവശ്യമാണ്."
    assert len(torch.samples) == 15992


def test_runner_rejects_unknown_fields_and_manifest_mismatch(tmp_path: Path, runner_module) -> None:
    audio = tmp_path / "audio.wav"
    model = tmp_path / "model"
    model.mkdir()
    _wav(audio)
    request = _request(audio, model)
    request["unexpected"] = True
    with pytest.raises(runner_module.RunnerError):
        runner_module.validate_request(request)

    (model / "shravya-model-manifest.json").write_text(
        json.dumps({"wrong": True}), encoding="utf-8"
    )
    with pytest.raises(runner_module.RunnerError, match="local_hybrid_model_mismatch"):
        runner_module.validate_manifest(model)


def test_runner_distinguishes_missing_manifest(tmp_path: Path, runner_module) -> None:
    with pytest.raises(runner_module.RunnerError, match="local_hybrid_model_manifest_missing"):
        runner_module.validate_manifest(tmp_path)


def test_runner_loads_exact_local_model_module_and_constructs_pinned_contract(
    tmp_path: Path, runner_module, monkeypatch
) -> None:
    model_path = tmp_path / "pinned-model"
    model_path.mkdir()
    module_path = _model_module(model_path)
    loaded_paths: list[Path] = []
    load_specification = runner_module.importlib.util.spec_from_file_location

    def capture_specification(module_name: str, location: Path):
        loaded_paths.append(Path(location))
        return load_specification(module_name, location)

    monkeypatch.setattr(
        runner_module.importlib.util, "spec_from_file_location", capture_specification
    )

    torch, model, _elapsed = _load_local_model(runner_module, monkeypatch, model_path)

    assert isinstance(torch, RuntimeTorch)
    assert loaded_paths == [module_path]
    assert model.config.ts_folder == str(model_path)
    assert model.eval_called is True
    assert callable(model)


def test_runner_fails_closed_when_local_model_module_is_missing(
    tmp_path: Path, runner_module, monkeypatch
) -> None:
    monkeypatch.setitem(sys.modules, "torch", RuntimeTorch())
    with pytest.raises(runner_module.RunnerError, match="local_hybrid_model_mismatch"):
        runner_module._lazy_model(tmp_path)


def test_runner_fails_closed_when_torch_is_unavailable(runner_module, monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "torch", None)

    with pytest.raises(runner_module.RunnerError, match="hybrid_runtime_dependency_unavailable"):
        runner_module._lazy_model(Path("unused"))


@pytest.mark.parametrize(
    "source, error_code",
    [
        ("raise RuntimeError('module failure')", "local_hybrid_model_mismatch"),
        ("class IndicASRModel: pass", "hybrid_model_contract_invalid"),
        (
            """
class IndicASRConfig:
    def __init__(self, *, ts_folder): pass
""",
            "hybrid_model_contract_invalid",
        ),
        (
            """
IndicASRConfig = None
class IndicASRModel: pass
""",
            "hybrid_model_contract_invalid",
        ),
        (
            """
class IndicASRConfig:
    def __init__(self, *, ts_folder): pass
IndicASRModel = None
""",
            "hybrid_model_contract_invalid",
        ),
        (
            """
class IndicASRConfig:
    def __init__(self, *, ts_folder): raise RuntimeError()
class IndicASRModel: pass
""",
            "hybrid_model_contract_invalid",
        ),
        (
            """
class IndicASRConfig:
    def __init__(self, *, ts_folder): pass
class IndicASRModel:
    def __init__(self, config): raise RuntimeError()
""",
            "hybrid_model_contract_invalid",
        ),
        (
            """
class IndicASRConfig:
    def __init__(self, *, ts_folder): pass
class IndicASRModel:
    def __init__(self, config): pass
""",
            "hybrid_model_contract_invalid",
        ),
    ],
)
def test_runner_fails_closed_for_invalid_local_model_contracts(
    tmp_path: Path, runner_module, monkeypatch, source: str, error_code: str
) -> None:
    _model_module(tmp_path, source)
    monkeypatch.setitem(sys.modules, "torch", RuntimeTorch())

    with pytest.raises(runner_module.RunnerError, match=error_code):
        runner_module._lazy_model(tmp_path)


def test_runner_fails_closed_when_local_module_specification_is_unavailable(
    tmp_path: Path, runner_module, monkeypatch
) -> None:
    _model_module(tmp_path)
    monkeypatch.setitem(sys.modules, "torch", RuntimeTorch())
    monkeypatch.setattr(
        runner_module.importlib.util, "spec_from_file_location", lambda *_args: None
    )

    with pytest.raises(runner_module.RunnerError, match="local_hybrid_model_mismatch"):
        runner_module._lazy_model(tmp_path)


def test_runner_fails_closed_when_local_module_loader_is_unavailable(
    tmp_path: Path, runner_module, monkeypatch
) -> None:
    _model_module(tmp_path)
    monkeypatch.setitem(sys.modules, "torch", RuntimeTorch())
    specification = importlib.util.spec_from_file_location("test", tmp_path / "model_onnx.py")
    assert specification is not None
    specification.loader = None
    monkeypatch.setattr(
        runner_module.importlib.util, "spec_from_file_location", lambda *_args: specification
    )

    with pytest.raises(runner_module.RunnerError, match="local_hybrid_model_mismatch"):
        runner_module._lazy_model(tmp_path)


def test_runner_source_has_no_huggingface_model_or_download_route() -> None:
    source = (
        Path(__file__).resolve().parents[2] / "scripts" / "indicconformer_runner.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        "AutoConfig",
        "AutoModel",
        "snapshot_download",
        "hf_hub_download",
        "requests.",
        "urllib.",
    ):
        assert forbidden not in source
