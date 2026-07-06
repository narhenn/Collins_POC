"""
pipeline3d — the production image→3D pipeline layers for Build-a-Twin.

Modular stages, one file per layer, all pure-Python and dependency-graceful:

    preprocess.py   ingest & quality gate: EXIF fix, resolution normalisation,
                    enhancement, background removal (rembg → heuristic →
                    worker-side), subject auto-crop, quality report
    params.py       TRELLIS generation parameters + quality presets
                    (draft / standard / ultra) — the model's real levers
    postprocess.py  GLB validation, mesh statistics, optional repair

The RunPod client (runpod_3d.py) drives these around the GPU call:

    upload → preprocess → TRELLIS(params) → postprocess → serve

Every stage returns a report dict so the whole run is explainable in the UI.
"""
from .params import TrellisParams, preset, QUALITY_PRESETS          # noqa: F401
from .preprocess import prepare_image                                # noqa: F401
from .postprocess import validate_glb, mesh_stats                    # noqa: F401
