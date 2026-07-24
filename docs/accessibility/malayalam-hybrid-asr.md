# Local Malayalam hybrid ASR

Shravya's optional `local_malayalam_hybrid` provider is an offline, teacher-review
workflow for a prepared local installation. It combines locally executed
faster-whisper speech boundaries with an AI4Bharat IndicConformer Malayalam-script
draft. IndicConformer is invoked through its callable model interface with the
locked positional `ml` and `ctc` arguments. It is not live cloud STT and it does
not report measured recognition accuracy or a combined confidence score.

The main backend environment remains lightweight. Install the model runtime only
in `.venv-indic-asr`, place the exact revision under
`.runtime/models/indic-conformer-600m-multilingual/e9b71b369c048e2c6b634d4c131061c34e441179`,
and include `shravya-model-manifest.json` with the locked model identity. The
runner directly loads that pinned snapshot's local `model_onnx.py`; it creates
`IndicASRConfig(ts_folder=<local snapshot directory>)` and then instantiates
`IndicASRModel` from that configuration. Runtime execution performs no model
download or Hugging Face cache fallback. The provider forces faster-whisper to
use local files only and supplies
`HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` to the child runner. Both models
must already be present locally. The child removes common Hugging Face token
environment variables; no Hugging Face token is required during offline inference.

Every hybrid draft requires the existing teacher review and transcript quality
gate. Raw faster-whisper configuration and evidence, raw IndicConformer text,
component timings, subprocess timing, and the resulting review segments are
retained separately for teacher-side audit. The top-level duration is the full
teacher wait time, not merely model inference. A hybrid transcript becomes
student-visible only after the established transcript and context approvals
succeed. No automatic English-term restoration or glossary correction occurs.

If the isolated runtime, runner, model directory, manifest, subprocess output,
local model code, or response contract is unavailable or invalid, Shravya fails closed and offers
the existing manual-transcript path. Unknown audio is never given a fabricated
transcript. Final real offline hardening is still pending; this documentation
does not claim demo-safe status or perfect ASR.
