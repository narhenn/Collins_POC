"""
params.py — the TRELLIS generation parameters and quality presets.

TRELLIS (microsoft/TRELLIS image-large) has two diffusion stages, each with its
own sampler settings — these are the model's real quality levers, which the old
pipeline never exposed (the worker ran silent defaults):

  sparse-structure stage  — decides WHAT geometry exists (coarse voxel field)
      ss_sampling_steps      more steps = better structure recovery, slower
      ss_guidance_strength   image adherence vs plausibility

  SLAT stage              — decides how it LOOKS (structured latents → mesh/
                            gaussians/texture)
      slat_sampling_steps    more steps = cleaner surfaces & texture
      slat_guidance_strength image adherence for appearance

  post-generation         — GLB extraction
      mesh_simplify          fraction of faces REMOVED (0.95 = aggressive)
      texture_size           baked texture resolution

Multi-image conditioning ("images": [...]) uses multiimage_algo
(stochastic | multidiffusion) — feed 2-4 views of the same object for a large
accuracy jump on complex objects.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field


@dataclass
class TrellisParams:
    seed: int = 1
    ss_sampling_steps: int = 12
    ss_guidance_strength: float = 7.5
    slat_sampling_steps: int = 12
    slat_guidance_strength: float = 3.0
    mesh_simplify: float = 0.95       # fraction of faces removed on extraction
    texture_size: int = 1024
    multiimage_algo: str = "stochastic"
    preprocess: bool = True           # worker-side rembg + recenter (authoritative)
    output_format: str = "glb"

    def payload(self) -> dict:
        return asdict(self)


# Quality presets exposed to the UI. "fast"/"high" keep the legacy route values
# working; draft/standard/ultra are the canonical names.
QUALITY_PRESETS: dict[str, TrellisParams] = {
    # quick preview — TRELLIS defaults, light texture
    "draft": TrellisParams(ss_sampling_steps=12, slat_sampling_steps=12,
                           texture_size=1024, mesh_simplify=0.95),
    # production default — the sweet spot (2-3x steps, 2K texture)
    "standard": TrellisParams(ss_sampling_steps=25, ss_guidance_strength=7.5,
                              slat_sampling_steps=25, slat_guidance_strength=3.0,
                              texture_size=2048, mesh_simplify=0.90),
    # maximum quality — full sampler budget, dense mesh
    "ultra": TrellisParams(ss_sampling_steps=50, ss_guidance_strength=8.0,
                           slat_sampling_steps=40, slat_guidance_strength=3.5,
                           texture_size=2048, mesh_simplify=0.80),
}
# legacy aliases used by the existing routes/UI
QUALITY_PRESETS["fast"] = QUALITY_PRESETS["draft"]
QUALITY_PRESETS["high"] = QUALITY_PRESETS["standard"]


def preset(quality: str | None) -> TrellisParams:
    return QUALITY_PRESETS.get((quality or "standard").lower(),
                               QUALITY_PRESETS["standard"])
