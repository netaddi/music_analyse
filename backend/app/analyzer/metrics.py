from __future__ import annotations

import math
from typing import Any

import numpy as np
import pyloudnorm as pyln
from scipy.signal import resample_poly

from app.config import settings
from app.schemas import ChartData, ChartSeries, TechnicalInfo

EPSILON = 1e-12
BAND_LIMITS = {
    "Sub": (20.0, 60.0),
    "Bass": (60.0, 120.0),
    "Low Mid": (150.0, 500.0),
    "Presence": (2000.0, 5000.0),
    "Sibilance": (5000.0, 9000.0),
    "Air": (10000.0, 16000.0),
}


def _as_mono(samples: np.ndarray) -> np.ndarray:
    if samples.shape[1] == 1:
        return samples[:, 0]
    return samples.mean(axis=1)


def _rms(signal: np.ndarray) -> float:
    array = np.asarray(signal, dtype=np.float64)
    if array.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(array * array)))


def _to_db(value: float) -> float:
    return float(20.0 * math.log10(max(value, EPSILON)))


def _power_to_db(value: float) -> float:
    return float(10.0 * math.log10(max(value, EPSILON)))


def _safe_float(value: float) -> float:
    return float(np.nan_to_num(value, nan=0.0, posinf=0.0, neginf=0.0))


def _safe_series(values: list[float]) -> list[float]:
    return [_safe_float(value) for value in values]


def _window_positions(length: int, window_size: int, hop_size: int) -> list[int]:
    if length <= window_size:
        return [0]
    positions = list(range(0, length - window_size + 1, hop_size))
    final_position = length - window_size
    if positions[-1] != final_position:
        positions.append(final_position)
    return positions


def _window_rms(signal: np.ndarray, sample_rate: int, window_seconds: float, hop_seconds: float) -> tuple[list[float], list[float]]:
    window_size = max(1, int(sample_rate * window_seconds))
    hop_size = max(1, int(sample_rate * hop_seconds))
    positions = _window_positions(signal.size, window_size, hop_size)
    values: list[float] = []
    times: list[float] = []

    for start in positions:
        end = min(signal.size, start + window_size)
        chunk = signal[start:end]
        values.append(_rms(chunk))
        times.append((start + (end - start) / 2) / sample_rate)

    return times, values


def _segment_loudness(segment: np.ndarray, meter: pyln.Meter) -> float:
    try:
        return _safe_float(float(meter.integrated_loudness(segment)))
    except (ValueError, ZeroDivisionError):
        if segment.ndim == 2:
            return _safe_float(_to_db(_rms(segment.mean(axis=1))))
        return _safe_float(_to_db(_rms(segment)))


def _window_loudness(samples: np.ndarray, sample_rate: int, meter: pyln.Meter, window_seconds: float, hop_seconds: float) -> tuple[list[float], list[float]]:
    window_size = max(1, int(sample_rate * window_seconds))
    hop_size = max(1, int(sample_rate * hop_seconds))
    positions = _window_positions(samples.shape[0], window_size, hop_size)
    values: list[float] = []
    times: list[float] = []

    for start in positions:
        end = min(samples.shape[0], start + window_size)
        chunk = samples[start:end]
        values.append(_segment_loudness(chunk, meter))
        times.append((start + (end - start) / 2) / sample_rate)

    return times, values


def _count_runs(mask: np.ndarray, minimum_length: int = 1) -> int:
    runs = 0
    current = 0
    for value in mask:
        if value:
            current += 1
            continue
        if current >= minimum_length:
            runs += 1
        current = 0
    if current >= minimum_length:
        runs += 1
    return runs


def _average_spectrum(signal: np.ndarray, sample_rate: int, frame_size: int = 4096, target_frames: int = 160) -> tuple[np.ndarray, np.ndarray]:
    if signal.size < frame_size:
        padded = np.zeros(frame_size, dtype=np.float64)
        padded[: signal.size] = signal.astype(np.float64)
        signal = padded

    available = max(0, signal.size - frame_size)
    frame_count = min(target_frames, max(1, available // max(1, frame_size // 2) + 1))
    starts = np.linspace(0, available, num=frame_count, dtype=int)
    window = np.hanning(frame_size)
    power_accumulator = np.zeros(frame_size // 2 + 1, dtype=np.float64)

    for start in starts:
        frame = signal[start : start + frame_size]
        if frame.size < frame_size:
            frame = np.pad(frame, (0, frame_size - frame.size))
        spectrum = np.fft.rfft(frame * window)
        power_accumulator += np.abs(spectrum) ** 2

    frequencies = np.fft.rfftfreq(frame_size, d=1.0 / sample_rate)
    return frequencies, power_accumulator / max(frame_count, 1)


def _band_power(frequencies: np.ndarray, power: np.ndarray, low_hz: float, high_hz: float) -> float:
    mask = (frequencies >= low_hz) & (frequencies < high_hz)
    if not np.any(mask):
        return 0.0
    return float(np.sum(power[mask]))


def _rolloff_hz(frequencies: np.ndarray, power: np.ndarray, threshold: float = 0.95) -> float:
    total = float(np.sum(power))
    if total <= 0.0:
        return 0.0
    cumulative = np.cumsum(power)
    index = int(np.searchsorted(cumulative, threshold * total, side="left"))
    index = min(index, frequencies.size - 1)
    return float(frequencies[index])


def _spectral_centroid(frequencies: np.ndarray, power: np.ndarray) -> float:
    total = float(np.sum(power))
    if total <= 0.0:
        return 0.0
    return float(np.sum(frequencies * power) / total)


def _spectral_flatness(power: np.ndarray) -> float:
    positive = np.maximum(power, EPSILON)
    return float(np.exp(np.mean(np.log(positive))) / np.mean(positive))


def _tonal_tilt(frequencies: np.ndarray, power: np.ndarray) -> float:
    mask = (frequencies >= 40.0) & (frequencies <= 16000.0)
    if np.count_nonzero(mask) < 4:
        return 0.0
    x_values = np.log10(np.maximum(frequencies[mask], 1.0))
    y_values = 10.0 * np.log10(np.maximum(power[mask], EPSILON))
    slope, _ = np.polyfit(x_values, y_values, 1)
    return float(slope)


def _true_peak(samples: np.ndarray) -> float:
    peaks: list[float] = []
    for channel_index in range(samples.shape[1]):
        channel = samples[:, channel_index]
        oversampled = resample_poly(channel.astype(np.float64), 4, 1)
        peaks.append(float(np.max(np.abs(oversampled))))
    return max(peaks, default=0.0)


def _safe_corr(left: np.ndarray, right: np.ndarray) -> float:
    if left.size == 0 or right.size == 0:
        return 0.0
    if float(np.std(left)) < EPSILON or float(np.std(right)) < EPSILON:
        return 1.0
    return float(np.corrcoef(left, right)[0, 1])


def _correlation_history(samples: np.ndarray, sample_rate: int) -> tuple[list[float], list[float]]:
    if samples.shape[1] < 2:
        return [0.0], [1.0]

    window_size = max(1, int(sample_rate * 0.5))
    hop_size = max(1, int(sample_rate * 0.25))
    positions = _window_positions(samples.shape[0], window_size, hop_size)
    times: list[float] = []
    values: list[float] = []

    left = samples[:, 0]
    right = samples[:, 1]
    for start in positions:
        end = min(samples.shape[0], start + window_size)
        values.append(_safe_corr(left[start:end], right[start:end]))
        times.append((start + (end - start) / 2) / sample_rate)

    return times, values


def _edge_silence(signal: np.ndarray, sample_rate: int, threshold_db: float, reverse: bool = False) -> float:
    threshold = 10 ** (threshold_db / 20.0)
    window_size = max(1, int(sample_rate * 0.05))
    probe = signal[::-1] if reverse else signal
    duration = 0.0

    for start in range(0, probe.size, window_size):
        chunk = probe[start : start + window_size]
        if _rms(chunk) > threshold:
            break
        duration += chunk.size / sample_rate

    return float(duration)


def _click_count(signal: np.ndarray) -> int:
    if signal.size < 4:
        return 0
    derivative = np.abs(np.diff(signal.astype(np.float64)))
    median = float(np.median(derivative))
    mad = float(np.median(np.abs(derivative - median))) + EPSILON
    threshold = median + 12.0 * mad
    spikes = derivative > threshold
    return _count_runs(spikes, minimum_length=1)


def _transient_density(window_rms: np.ndarray) -> float:
    if window_rms.size < 3:
        return 0.0
    deltas = np.diff(window_rms)
    threshold = float(np.quantile(np.abs(deltas), 0.9))
    if threshold <= 0.0:
        return 0.0
    return float(np.mean(np.abs(deltas) >= threshold))


def _waveform_chart(signal: np.ndarray, sample_rate: int) -> ChartData:
    points = max(60, settings.report_points)
    block_size = max(1, signal.size // points)
    x_values: list[float] = []
    y_values: list[float] = []

    for index in range(0, signal.size, block_size):
        block = signal[index : index + block_size]
        if block.size == 0:
            continue
        x_values.append(index / sample_rate)
        y_values.append(float(np.max(np.abs(block))))

    return ChartData(
        kind="line",
        title="Waveform Overview",
        x_label="Time (s)",
        y_label="Peak amplitude",
        x=x_values,
        series=[ChartSeries(name="Envelope", values=y_values)],
    )


def _loudness_chart(short_term: tuple[list[float], list[float]], momentary: tuple[list[float], list[float]]) -> ChartData:
    return ChartData(
        kind="line",
        title="Loudness Over Time",
        x_label="Time (s)",
        y_label="LUFS",
        x=short_term[0],
        series=[
            ChartSeries(name="Short-term", values=_safe_series(short_term[1])),
            ChartSeries(name="Momentary", values=_safe_series(momentary[1])),
        ],
    )


def _spectrum_chart(band_ratios: dict[str, float]) -> ChartData:
    labels = list(band_ratios.keys())
    values = [round(ratio * 100.0, 2) for ratio in band_ratios.values()]
    return ChartData(
        kind="bar",
        title="Spectral Balance",
        x_label="Band",
        y_label="Energy share (%)",
        labels=labels,
        series=[ChartSeries(name="Energy share", values=values)],
    )


def _correlation_chart(correlation_history: tuple[list[float], list[float]]) -> ChartData:
    return ChartData(
        kind="line",
        title="Stereo Correlation",
        x_label="Time (s)",
        y_label="Correlation",
        x=correlation_history[0],
        series=[ChartSeries(name="Correlation", values=correlation_history[1])],
    )


def compute_metrics(samples: np.ndarray, technical_info: TechnicalInfo) -> tuple[dict[str, Any], dict[str, ChartData]]:
    sample_rate = technical_info.sample_rate
    mono = _as_mono(samples)

    overall_rms = _rms(samples)
    sample_peak = float(np.max(np.abs(samples)))
    true_peak = _true_peak(samples)
    sample_peak_dbfs = _to_db(sample_peak)
    true_peak_dbtp = _to_db(true_peak)
    rms_dbfs = _to_db(overall_rms)

    meter = pyln.Meter(sample_rate)
    try:
        integrated_lufs = float(meter.integrated_loudness(samples if samples.shape[1] > 1 else mono))
    except (ValueError, ZeroDivisionError):
        integrated_lufs = rms_dbfs
    integrated_lufs = _safe_float(integrated_lufs)

    try:
        lra_lu = float(meter.loudness_range(samples if samples.shape[1] > 1 else mono))
    except (ValueError, ZeroDivisionError):
        lra_lu = 0.0
    lra_lu = _safe_float(lra_lu)

    short_term = _window_loudness(samples, sample_rate, meter, window_seconds=3.0, hop_seconds=1.0)
    momentary = _window_loudness(samples, sample_rate, meter, window_seconds=0.4, hop_seconds=0.4)
    short_term = (short_term[0], _safe_series(short_term[1]))
    momentary = (momentary[0], _safe_series(momentary[1]))
    _, rms_windows = _window_rms(mono, sample_rate, window_seconds=0.4, hop_seconds=0.1)
    rms_window_array = np.asarray(rms_windows, dtype=np.float64)
    rms_window_dbfs = np.array([_to_db(value) for value in rms_window_array], dtype=np.float64)

    crest_factor_db = sample_peak_dbfs - rms_dbfs
    plr_db = true_peak_dbtp - integrated_lufs
    dynamic_range_proxy_db = float(np.quantile(rms_window_dbfs, 0.9) - np.quantile(rms_window_dbfs, 0.1)) if rms_window_dbfs.size else 0.0
    transient_density = _transient_density(rms_window_array)

    clipping_mask = np.max(np.abs(samples), axis=1) >= 0.999
    sample_clipping_count = int(np.sum(np.abs(samples) >= 0.999))
    clipped_segment_count = _count_runs(clipping_mask, minimum_length=3)
    flat_top_mask = (np.abs(mono[:-1]) > 0.98) & (np.abs(np.diff(mono)) < 1e-5)
    flat_top_segment_count = _count_runs(flat_top_mask, minimum_length=4)

    freqs, avg_power = _average_spectrum(mono, sample_rate)
    total_music_power = _band_power(freqs, avg_power, 20.0, min(20000.0, sample_rate / 2.0))
    band_powers = {name: _band_power(freqs, avg_power, low, high) for name, (low, high) in BAND_LIMITS.items()}
    band_ratios = {
        name: float(power / max(total_music_power, EPSILON))
        for name, power in band_powers.items()
    }
    band_levels_db = {name: _power_to_db(power) for name, power in band_powers.items()}
    tonal_tilt = _tonal_tilt(freqs, avg_power)
    spectral_centroid_hz = _spectral_centroid(freqs, avg_power)
    spectral_flatness = _spectral_flatness(avg_power)
    rolloff_hz = _rolloff_hz(freqs, avg_power)

    low_freq_energy_ratio = float((_band_power(freqs, avg_power, 20.0, 120.0)) / max(total_music_power, EPSILON))
    sub_to_bass_ratio = float(band_powers["Sub"] / max(band_powers["Bass"], EPSILON))
    low_mid_ratio = band_ratios["Low Mid"]
    presence_ratio = band_ratios["Presence"]
    sibilance_ratio = band_ratios["Sibilance"]
    air_ratio = band_ratios["Air"]

    if samples.shape[1] > 1:
        left = samples[:, 0]
        right = samples[:, 1]
        lr_rms_diff_db = abs(_to_db(_rms(left)) - _to_db(_rms(right)))
        mid = (left + right) * 0.5
        side = (left - right) * 0.5
        mid_rms = _rms(mid)
        side_rms = _rms(side)
        stereo_width = float(side_rms / max(mid_rms + side_rms, EPSILON))
        mid_side_ratio_db = _to_db(mid_rms) - _to_db(side_rms)
        correlation = _safe_corr(left, right)
        correlation_history = _correlation_history(samples, sample_rate)
        negative_correlation_ratio = float(np.mean(np.asarray(correlation_history[1]) < -0.1))
        mono_loss_db = _to_db(_rms(samples)) - _to_db(_rms(mid))

        mid_freqs, mid_power = _average_spectrum(mid, sample_rate)
        side_freqs, side_power = _average_spectrum(side, sample_rate)
        mid_low_power = _band_power(mid_freqs, mid_power, 20.0, 120.0)
        side_low_power = _band_power(side_freqs, side_power, 20.0, 120.0)
        low_freq_side_ratio = float(side_low_power / max(mid_low_power + side_low_power, EPSILON))
    else:
        lr_rms_diff_db = 0.0
        stereo_width = 0.0
        mid_side_ratio_db = 99.0
        correlation = 1.0
        correlation_history = ([0.0], [1.0])
        negative_correlation_ratio = 0.0
        mono_loss_db = 0.0
        low_freq_side_ratio = 0.0

    leading_silence_sec = _edge_silence(mono, sample_rate, threshold_db=-55.0)
    trailing_silence_sec = _edge_silence(mono, sample_rate, threshold_db=-55.0, reverse=True)
    noise_floor_dbfs = float(np.quantile(rms_window_dbfs, 0.1)) if rms_window_dbfs.size else -120.0
    dc_offset = float(np.mean(samples))
    hum_power = sum(_band_power(freqs, avg_power, center - 2.0, center + 2.0) for center in (50.0, 60.0, 100.0, 120.0))
    hum_ratio = float(hum_power / max(_band_power(freqs, avg_power, 20.0, 200.0), EPSILON))
    click_count = _click_count(mono)
    platform_attenuation_db = max(0.0, integrated_lufs - settings.target_lufs)

    metrics: dict[str, Any] = {
        "integrated_lufs": round(_safe_float(integrated_lufs), 2),
        "momentary_lufs_max": round(max(momentary[1], default=integrated_lufs), 2),
        "short_term_lufs_max": round(max(short_term[1], default=integrated_lufs), 2),
        "lra_lu": round(_safe_float(lra_lu), 2),
        "true_peak_dbtp": round(_safe_float(true_peak_dbtp), 2),
        "sample_peak_dbfs": round(_safe_float(sample_peak_dbfs), 2),
        "rms_dbfs": round(_safe_float(rms_dbfs), 2),
        "platform_attenuation_db": round(_safe_float(platform_attenuation_db), 2),
        "crest_factor_db": round(_safe_float(crest_factor_db), 2),
        "plr_db": round(_safe_float(plr_db), 2),
        "dynamic_range_proxy_db": round(_safe_float(dynamic_range_proxy_db), 2),
        "transient_density": round(_safe_float(transient_density), 4),
        "sample_clipping_count": sample_clipping_count,
        "clipped_segment_count": clipped_segment_count,
        "flat_top_segment_count": flat_top_segment_count,
        "lr_rms_diff_db": round(_safe_float(lr_rms_diff_db), 2),
        "stereo_width": round(_safe_float(stereo_width), 4),
        "mid_side_ratio_db": round(_safe_float(mid_side_ratio_db), 2),
        "correlation": round(_safe_float(correlation), 4),
        "negative_correlation_ratio": round(_safe_float(negative_correlation_ratio), 4),
        "mono_loss_db": round(_safe_float(mono_loss_db), 2),
        "band_ratios": {name: round(_safe_float(value), 4) for name, value in band_ratios.items()},
        "band_levels_db": {name: round(_safe_float(value), 2) for name, value in band_levels_db.items()},
        "tonal_tilt": round(_safe_float(tonal_tilt), 2),
        "spectral_centroid_hz": round(_safe_float(spectral_centroid_hz), 2),
        "spectral_flatness": round(_safe_float(spectral_flatness), 4),
        "rolloff_hz": round(_safe_float(rolloff_hz), 2),
        "low_freq_energy_ratio": round(_safe_float(low_freq_energy_ratio), 4),
        "sub_to_bass_ratio": round(_safe_float(sub_to_bass_ratio), 4),
        "low_mid_ratio": round(_safe_float(low_mid_ratio), 4),
        "presence_ratio": round(_safe_float(presence_ratio), 4),
        "sibilance_ratio": round(_safe_float(sibilance_ratio), 4),
        "air_ratio": round(_safe_float(air_ratio), 4),
        "low_freq_side_ratio": round(_safe_float(low_freq_side_ratio), 4),
        "noise_floor_dbfs": round(_safe_float(noise_floor_dbfs), 2),
        "leading_silence_sec": round(_safe_float(leading_silence_sec), 2),
        "trailing_silence_sec": round(_safe_float(trailing_silence_sec), 2),
        "dc_offset": round(_safe_float(dc_offset), 6),
        "hum_ratio": round(_safe_float(hum_ratio), 4),
        "click_count": click_count,
    }

    charts = {
        "waveform": _waveform_chart(mono, sample_rate),
        "loudness": _loudness_chart(short_term, momentary),
        "spectrum": _spectrum_chart(metrics["band_ratios"]),
        "correlation": _correlation_chart(correlation_history),
    }

    return metrics, charts
