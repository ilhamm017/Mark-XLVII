from __future__ import annotations

from typing import Iterable

import numpy as np
import sounddevice as sd


_INPUT_RATE_CANDIDATES: tuple[int, ...] = (16000, 48000, 44100, 24000)
_OUTPUT_RATE_CANDIDATES: tuple[int, ...] = (48000, 44100, 24000, 16000)


def _default_device_index(kind: str) -> int | None:
    try:
        default = sd.default.device
        if isinstance(default, (tuple, list)) and len(default) == 2:
            index = default[0] if kind == "input" else default[1]
            if isinstance(index, int) and index >= 0:
                return index
    except Exception:
        pass

    try:
        info = sd.query_devices(None, kind)
        index = info.get("index")
        if isinstance(index, int) and index >= 0:
            return index
    except Exception:
        pass

    return None


def select_supported_rate(
    kind: str,
    candidates: Iterable[int],
    *,
    channels: int = 1,
    dtype: str = "int16",
) -> tuple[int, int | None]:
    """
    Pick the first PortAudio sample rate that this host/device accepts.

    Returns (sample_rate, device_index). If no candidate matches, falls back
    to the device's reported default samplerate and then the final candidate.
    """
    device = _default_device_index(kind)
    checker = sd.check_input_settings if kind == "input" else sd.check_output_settings

    for rate in candidates:
        try:
            checker(device=device, samplerate=rate, channels=channels, dtype=dtype)
            return rate, device
        except Exception:
            continue

    try:
        info = sd.query_devices(device, kind)
        return int(round(info["default_samplerate"])), device
    except Exception:
        fallback = next(iter(candidates))
        return fallback, device


def resample_int16_mono(samples, src_rate: int, dst_rate: int) -> np.ndarray:
    """
    Resample mono int16 PCM using linear interpolation.

    This is intentionally dependency-free so it works in the current venv.
    """
    arr = np.asarray(samples)
    if arr.ndim > 1:
        arr = arr.reshape(-1)
    if arr.size == 0 or src_rate == dst_rate:
        return arr.astype(np.int16, copy=False)

    src_len = arr.shape[0]
    dst_len = max(1, int(round(src_len * dst_rate / src_rate)))
    x_old = np.arange(src_len, dtype=np.float64)
    x_new = np.linspace(0.0, float(src_len - 1), num=dst_len, dtype=np.float64)
    y = np.interp(x_new, x_old, arr.astype(np.float64))
    return np.clip(np.rint(y), -32768, 32767).astype(np.int16)


def resample_float32_mono(samples, src_rate: int, dst_rate: int) -> np.ndarray:
    arr = np.asarray(samples, dtype=np.float32)
    if arr.ndim > 1:
        arr = arr.reshape(-1)
    if arr.size == 0 or src_rate == dst_rate:
        return arr.astype(np.float32, copy=False)

    src_len = arr.shape[0]
    dst_len = max(1, int(round(src_len * dst_rate / src_rate)))
    x_old = np.arange(src_len, dtype=np.float64)
    x_new = np.linspace(0.0, float(src_len - 1), num=dst_len, dtype=np.float64)
    y = np.interp(x_new, x_old, arr.astype(np.float64))
    return y.astype(np.float32)


def default_input_rate() -> tuple[int, int | None]:
    return select_supported_rate("input", _INPUT_RATE_CANDIDATES)


def default_output_rate() -> tuple[int, int | None]:
    return select_supported_rate("output", _OUTPUT_RATE_CANDIDATES)
