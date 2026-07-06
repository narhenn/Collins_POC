"""
preprocess.py — the input layer of the image→3D pipeline.

TRELLIS is a single-OBJECT generator trained on clean, centred subjects; most
"bad model" outcomes are bad INPUTS (busy background, tiny subject, blur,
multiple objects). This stage turns an arbitrary upload into the best possible
conditioning image and tells the caller (and the UI) what it did and what risk
remains:

    1. load       — EXIF-orientation fix, RGBA
    2. analyze    — resolution / blur / background business / subject coverage
    3. enhance    — resolution normalisation (upscale small, cap huge),
                    gentle autocontrast + unsharp
    4. isolate    — background removal: rembg if installed, else a border-color
                    heuristic when the background is plain, else defer to the
                    GPU worker (which runs full rembg in preprocess=True)
    5. frame      — auto-crop to the subject with margin, pad to square

Returns (png_bytes, report). Never raises on quality problems — it fixes what
it can and reports the rest as warnings.
"""
from __future__ import annotations

import io
import math

import numpy as np
from PIL import Image, ImageFilter, ImageOps

TARGET = 1024          # normalised working resolution (worker downsizes itself)
MIN_SIDE = 512         # below this we upscale
MAX_SIDE = 2048        # above this we downscale (bandwidth + no quality gain)


# ── analysis helpers ──────────────────────────────────────────────────

def _blur_score(gray: np.ndarray) -> float:
    """Variance of a Laplacian — classic sharpness measure (higher = sharper)."""
    lap = (np.abs(np.diff(gray, 2, axis=0)).mean()
           + np.abs(np.diff(gray, 2, axis=1)).mean())
    return float(lap)


def _border_stats(arr: np.ndarray, band: int = 12) -> tuple[np.ndarray, float]:
    """(mean border colour, border colour std) — plain backgrounds have low std."""
    b = np.concatenate([
        arr[:band].reshape(-1, arr.shape[2]),
        arr[-band:].reshape(-1, arr.shape[2]),
        arr[:, :band].reshape(-1, arr.shape[2]),
        arr[:, -band:].reshape(-1, arr.shape[2]),
    ]).astype(np.float32)
    return b.mean(axis=0), float(b.std(axis=0).mean())


# ── background removal ───────────────────────────────────────────────

def _rembg(img: Image.Image):
    """Real matting if rembg is installed (optional heavy dep)."""
    try:
        from rembg import remove  # type: ignore
    except Exception:
        return None
    try:
        return remove(img)
    except Exception:
        return None


def _heuristic_cutout(img: Image.Image, border_std_limit: float = 28.0):
    """Plain-background cutout: alpha = distance from the border colour.
    Only used when the border is uniform enough to trust; busy scenes are
    left for the GPU worker's rembg."""
    arr = np.asarray(img.convert("RGB"), dtype=np.float32)
    mean, std = _border_stats(arr)
    if std > border_std_limit:
        return None                                    # busy background — skip
    dist = np.linalg.norm(arr - mean[None, None, :], axis=2)
    thresh = max(30.0, std * 2.5)
    alpha = np.clip((dist - thresh * 0.5) / max(1e-6, thresh), 0.0, 1.0)
    a_img = Image.fromarray((alpha * 255).astype(np.uint8), "L")
    # despeckle + soften the matte edge
    a_img = a_img.filter(ImageFilter.MedianFilter(5)).filter(
        ImageFilter.GaussianBlur(1.2))
    out = img.convert("RGBA")
    out.putalpha(a_img)
    return out


def _subject_bbox(alpha: np.ndarray, thresh: int = 24):
    ys, xs = np.where(alpha > thresh)
    if len(xs) < 32:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


# ── the stage ─────────────────────────────────────────────────────────

def prepare_image(data: bytes, remove_background: bool = True) -> tuple[bytes, dict]:
    """Run the full input layer. Returns (png_bytes, report)."""
    report: dict = {"steps": [], "warnings": [], "server_preprocess": True}

    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img)
    report["input"] = {"size": list(img.size), "mode": img.mode,
                       "format": img.format}
    img = img.convert("RGBA")

    # 2. analyze
    gray = np.asarray(img.convert("L"), dtype=np.float32)
    blur = _blur_score(gray)
    _, border_std = _border_stats(np.asarray(img.convert("RGB"), dtype=np.float32))
    report["analysis"] = {"blur_score": round(blur, 2),
                          "border_std": round(border_std, 1)}
    if blur < 1.5:
        report["warnings"].append(
            "image looks blurry — expect soft geometry; retake sharper if possible")
    if min(img.size) < 300:
        report["warnings"].append(
            f"very low resolution ({img.size[0]}x{img.size[1]}) — detail will be invented")
    if border_std > 55:
        report["warnings"].append(
            "busy background / possible multi-object scene — TRELLIS reconstructs "
            "ONE object; crop to a single subject for best results")

    # 3. enhance: resolution normalisation + gentle contrast
    w, h = img.size
    scale = 1.0
    if max(w, h) > MAX_SIDE:
        scale = MAX_SIDE / max(w, h)
    elif min(w, h) < MIN_SIDE:
        scale = min(4.0, TARGET / min(w, h))
    if scale != 1.0:
        img = img.resize((max(1, round(w * scale)), max(1, round(h * scale))),
                         Image.LANCZOS)
        report["steps"].append(f"resized {w}x{h} → {img.size[0]}x{img.size[1]}")
    rgb = img.convert("RGB")
    rgb = ImageOps.autocontrast(rgb, cutoff=1)
    rgb = rgb.filter(ImageFilter.UnsharpMask(radius=2, percent=60, threshold=3))
    alpha_in = img.getchannel("A")
    img = rgb.convert("RGBA")
    img.putalpha(alpha_in)
    report["steps"].append("autocontrast + unsharp")

    # 4. isolate the subject
    cut = None
    already_cut = np.asarray(alpha_in).min() < 200        # upload had transparency
    if already_cut:
        cut = img
        report["steps"].append("upload already has alpha — kept")
        report["server_preprocess"] = False
    elif remove_background:
        cut = _rembg(img)
        if cut is not None:
            report["steps"].append("background removed (rembg)")
            report["server_preprocess"] = False
        else:
            cut = _heuristic_cutout(img)
            if cut is not None:
                report["steps"].append("background removed (plain-bg heuristic)")
                # keep worker-side rembg on as the authoritative pass
            else:
                report["steps"].append(
                    "background left for GPU worker (rembg on server)")
    img = cut or img

    # 5. frame: crop to subject + margin, pad square
    alpha = np.asarray(img.getchannel("A"))
    bbox = _subject_bbox(alpha)
    if bbox:
        x0, y0, x1, y1 = bbox
        coverage = ((x1 - x0) * (y1 - y0)) / (img.size[0] * img.size[1])
        report["analysis"]["subject_coverage"] = round(coverage, 3)
        if coverage < 0.05:
            report["warnings"].append(
                "subject is tiny in frame — reconstruction quality will suffer")
        m = int(0.12 * max(x1 - x0, y1 - y0))
        x0, y0 = max(0, x0 - m), max(0, y0 - m)
        x1, y1 = min(img.size[0], x1 + m), min(img.size[1], y1 + m)
        img = img.crop((x0, y0, x1, y1))
        report["steps"].append("auto-cropped to subject")
    side = max(img.size)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(img, ((side - img.size[0]) // 2, (side - img.size[1]) // 2))
    img = canvas
    if max(img.size) > TARGET:
        img = img.resize((TARGET, TARGET), Image.LANCZOS)
    report["output"] = {"size": list(img.size)}

    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue(), report
