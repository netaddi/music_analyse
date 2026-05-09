from __future__ import annotations

from dataclasses import dataclass

from app.schemas import AnalysisSummary, CategoryReport, Recommendation, TechnicalInfo
from app.scoring.thresholds import THRESHOLDS, WEIGHTS


@dataclass(slots=True)
class ScoredReport:
    summary: AnalysisSummary
    categories: list[CategoryReport]
    recommendations: list[Recommendation]


def _clamp(score: float) -> float:
    return round(max(0.0, min(100.0, score)), 1)


def _severity(score: float) -> str:
    if score >= 90.0:
        return "info"
    if score >= 75.0:
        return "minor"
    if score >= 60.0:
        return "moderate"
    return "major"


def _confidence(duration_seconds: float, evidence_count: int) -> float:
    duration_bonus = min(duration_seconds / 1200.0, 0.18)
    evidence_bonus = min(evidence_count * 0.02, 0.1)
    return round(min(0.98, 0.68 + duration_bonus + evidence_bonus), 2)


def _category(
    *,
    slug: str,
    name: str,
    score: float,
    summary: str,
    details: str,
    evidence: list[str],
    suggestions: list[str],
    duration_seconds: float,
) -> CategoryReport:
    clamped_score = _clamp(score)
    return CategoryReport(
        slug=slug,
        name=name,
        score=clamped_score,
        severity=_severity(clamped_score),
        summary=summary,
        details=details,
        evidence=evidence,
        suggestions=suggestions,
        confidence=_confidence(duration_seconds, len(evidence)),
    )


def _recommendation(category: CategoryReport) -> Recommendation:
    return Recommendation(
        id=f"rec-{category.slug}",
        category_slug=category.slug,
        title=category.name,
        severity=category.severity,
        summary=category.summary,
        evidence=category.evidence,
        actions=category.suggestions,
        confidence=category.confidence,
    )


def _risk_label(score: float) -> str:
    if score >= 90.0:
        return "stable"
    if score >= 75.0:
        return "release-ready with checks"
    if score >= 60.0:
        return "noticeable technical risk"
    if score >= 40.0:
        return "high technical risk"
    return "critical technical risk"


def score_analysis(metrics: dict[str, float | int | dict[str, float]], technical_info: TechnicalInfo) -> ScoredReport:
    duration = technical_info.duration_seconds
    band_ratios = metrics["band_ratios"]
    assert isinstance(band_ratios, dict)

    categories: list[CategoryReport] = []

    loudness_score = 100.0
    loudness_evidence: list[str] = []
    loudness_suggestions: list[str] = []
    integrated_lufs = float(metrics["integrated_lufs"])
    true_peak_dbtp = float(metrics["true_peak_dbtp"])
    attenuation_db = float(metrics["platform_attenuation_db"])
    if integrated_lufs > THRESHOLDS["hot_lufs"]:
        loudness_score -= (integrated_lufs - THRESHOLDS["hot_lufs"]) * 7.0
        loudness_evidence.append(f"Integrated loudness is {integrated_lufs:.1f} LUFS, hotter than a typical streaming master.")
        loudness_suggestions.append("Ease off limiter drive or raise the threshold to recover headroom.")
    if integrated_lufs < THRESHOLDS["quiet_lufs"]:
        loudness_score -= (THRESHOLDS["quiet_lufs"] - integrated_lufs) * 3.0
        loudness_evidence.append(f"Integrated loudness is {integrated_lufs:.1f} LUFS, which may feel underpowered outside dynamic genres.")
        loudness_suggestions.append("Consider a gentle loudness lift if the release target is modern streaming playback.")
    if true_peak_dbtp > THRESHOLDS["true_peak_ceiling"]:
        loudness_score -= (true_peak_dbtp - THRESHOLDS["true_peak_ceiling"]) * 18.0
        loudness_evidence.append(f"True peak reaches {true_peak_dbtp:.1f} dBTP, leaving limited codec headroom.")
        loudness_suggestions.append("Lower the output ceiling to around -1.0 dBTP before export.")
    if attenuation_db > 5.0:
        loudness_score -= (attenuation_db - 5.0) * 4.0
        loudness_evidence.append(f"Streaming platforms may turn this down by roughly {attenuation_db:.1f} dB.")
        loudness_suggestions.append("Aim closer to -14 LUFS if you want less loudness normalization loss.")
    categories.append(
        _category(
            slug="loudness",
            name="Loudness",
            score=loudness_score,
            summary="Streaming loudness and headroom look controlled." if loudness_score >= 90.0 else "The loudness target is likely to cause normalization or headroom issues.",
            details="This category weighs integrated loudness, true peak headroom, and the likely normalization hit on streaming platforms.",
            evidence=loudness_evidence,
            suggestions=loudness_suggestions or ["Keep the current loudness target if it matches the intended release context."],
            duration_seconds=duration,
        )
    )

    dynamics_score = 100.0
    dynamics_evidence: list[str] = []
    dynamics_suggestions: list[str] = []
    crest_factor_db = float(metrics["crest_factor_db"])
    plr_db = float(metrics["plr_db"])
    dynamic_range_proxy_db = float(metrics["dynamic_range_proxy_db"])
    transient_density = float(metrics["transient_density"])
    if crest_factor_db < THRESHOLDS["minimum_crest_db"]:
        dynamics_score -= (THRESHOLDS["minimum_crest_db"] - crest_factor_db) * 6.0
        dynamics_evidence.append(f"Crest factor is {crest_factor_db:.1f} dB, which suggests limited transient headroom.")
        dynamics_suggestions.append("Back off bus compression or limiter gain reduction to restore punch.")
    if plr_db < THRESHOLDS["minimum_plr_db"]:
        dynamics_score -= (THRESHOLDS["minimum_plr_db"] - plr_db) * 5.0
        dynamics_evidence.append(f"Peak-to-loudness ratio is {plr_db:.1f} dB, pointing to a dense master.")
        dynamics_suggestions.append("Review the final limiter stage and long-release compression settings.")
    if dynamic_range_proxy_db < THRESHOLDS["minimum_dynamic_proxy_db"]:
        dynamics_score -= (THRESHOLDS["minimum_dynamic_proxy_db"] - dynamic_range_proxy_db) * 5.0
        dynamics_evidence.append(f"Short-window dynamic spread is {dynamic_range_proxy_db:.1f} dB.")
        dynamics_suggestions.append("Let verses, breakdowns, or intros breathe more before the loudest sections.")
    if transient_density < 0.05:
        dynamics_score -= 5.0
        dynamics_evidence.append("Transient movement is unusually flat across the track.")
        dynamics_suggestions.append("Protect drum and consonant transients with slower attack settings or parallel processing.")
    categories.append(
        _category(
            slug="dynamics",
            name="Dynamics",
            score=dynamics_score,
            summary="The mix keeps useful contrast between loud and quiet passages." if dynamics_score >= 90.0 else "The dynamics profile suggests compression or limiting is dominating the master.",
            details="The dynamics score combines crest factor, peak-to-loudness ratio, short-window spread, and transient density.",
            evidence=dynamics_evidence,
            suggestions=dynamics_suggestions or ["The current dynamics profile is balanced for a modern release."],
            duration_seconds=duration,
        )
    )

    clipping_score = 100.0
    clipping_evidence: list[str] = []
    clipping_suggestions: list[str] = []
    sample_clipping_count = int(metrics["sample_clipping_count"])
    clipped_segment_count = int(metrics["clipped_segment_count"])
    flat_top_segment_count = int(metrics["flat_top_segment_count"])
    if sample_clipping_count >= THRESHOLDS["clipping_minor"]:
        clipping_score -= min(55.0, sample_clipping_count * 2.0)
        clipping_evidence.append(f"Detected {sample_clipping_count} clipped samples and {clipped_segment_count} clipped runs.")
        clipping_suggestions.append("Reduce the final output level and reprint before lossy encoding.")
    if flat_top_segment_count > 0:
        clipping_score -= min(25.0, flat_top_segment_count * 4.0)
        clipping_evidence.append(f"Detected {flat_top_segment_count} flat-top regions, which often point to limiter flattening.")
        clipping_suggestions.append("Check whether the limiter is shaving sustained peaks instead of brief transients.")
    categories.append(
        _category(
            slug="clipping",
            name="Clipping and Peaks",
            score=clipping_score,
            summary="Peak behavior looks clean." if clipping_score >= 90.0 else "Peak handling shows clipping or aggressive flattening risk.",
            details="This category checks direct clipping, repeated clipped runs, and flat-top waveforms that often correlate with distortion.",
            evidence=clipping_evidence,
            suggestions=clipping_suggestions or ["Peak management is currently under control."],
            duration_seconds=duration,
        )
    )

    stereo_score = 100.0
    stereo_evidence: list[str] = []
    stereo_suggestions: list[str] = []
    lr_rms_diff_db = float(metrics["lr_rms_diff_db"])
    stereo_width = float(metrics["stereo_width"])
    if technical_info.channels == 1:
        stereo_score -= 8.0
        stereo_evidence.append("The file is mono, so stereo width checks are naturally limited.")
        stereo_suggestions.append("Keep the mono presentation if it is intentional, or export a stereo master if the mix requires width.")
    if lr_rms_diff_db > THRESHOLDS["stereo_balance_db"]:
        stereo_score -= (lr_rms_diff_db - THRESHOLDS["stereo_balance_db"]) * 12.0
        stereo_evidence.append(f"Left/right RMS differs by {lr_rms_diff_db:.1f} dB, suggesting image imbalance.")
        stereo_suggestions.append("Review pan law, stereo bus processing, and channel-matched limiting.")
    if technical_info.channels > 1 and stereo_width < THRESHOLDS["stereo_width_low"]:
        stereo_score -= (THRESHOLDS["stereo_width_low"] - stereo_width) * 160.0
        stereo_evidence.append(f"Stereo width proxy is {stereo_width:.2f}, which is unusually narrow.")
        stereo_suggestions.append("Consider whether ambience, side content, or width automation is missing.")
    if stereo_width > THRESHOLDS["stereo_width_high"]:
        stereo_score -= (stereo_width - THRESHOLDS["stereo_width_high"]) * 120.0
        stereo_evidence.append(f"Stereo width proxy is {stereo_width:.2f}, which may feel exaggerated.")
        stereo_suggestions.append("Trim wide-side processing if the center feels unstable on speakers.")
    categories.append(
        _category(
            slug="stereo",
            name="Stereo Field",
            score=stereo_score,
            summary="The stereo image looks centered and controlled." if stereo_score >= 90.0 else "The stereo field may need balance or width refinement.",
            details="Stereo scoring combines channel balance and a mid/side-derived width proxy.",
            evidence=stereo_evidence,
            suggestions=stereo_suggestions or ["Stereo balance and width are consistent with a stable mix image."],
            duration_seconds=duration,
        )
    )

    phase_score = 100.0
    phase_evidence: list[str] = []
    phase_suggestions: list[str] = []
    correlation = float(metrics["correlation"])
    negative_correlation_ratio = float(metrics["negative_correlation_ratio"])
    mono_loss_db = float(metrics["mono_loss_db"])
    if correlation < THRESHOLDS["correlation_warning"]:
        phase_score -= (THRESHOLDS["correlation_warning"] - correlation) * 40.0
        phase_evidence.append(f"Global stereo correlation is {correlation:.2f}, which indicates phase tension.")
        phase_suggestions.append("Check stereo wideners, polarity inversion, and time-offset effects on key elements.")
    if negative_correlation_ratio > THRESHOLDS["negative_correlation_ratio"]:
        phase_score -= (negative_correlation_ratio - THRESHOLDS["negative_correlation_ratio"]) * 140.0
        phase_evidence.append(f"Negative correlation appears in {negative_correlation_ratio * 100:.1f}% of analysis windows.")
        phase_suggestions.append("Audit chorus, Haas-delay, and decorrelation processing for mono compatibility.")
    if mono_loss_db > THRESHOLDS["mono_loss_warning_db"]:
        phase_score -= (mono_loss_db - THRESHOLDS["mono_loss_warning_db"]) * 16.0
        phase_evidence.append(f"Collapsing to mono loses about {mono_loss_db:.1f} dB of level.")
        phase_suggestions.append("Reduce low-level out-of-phase material and confirm mono fold-down on a bus meter.")
    categories.append(
        _category(
            slug="phase",
            name="Phase and Mono Compatibility",
            score=phase_score,
            summary="Mono compatibility looks acceptable." if phase_score >= 90.0 else "Phase relationships may compromise playback on mono or speaker-summed systems.",
            details="This category checks average correlation, the share of negative-correlation windows, and the mono fold-down loss.",
            evidence=phase_evidence,
            suggestions=phase_suggestions or ["Phase behavior is stable enough for typical stereo playback."],
            duration_seconds=duration,
        )
    )

    spectral_score = 100.0
    spectral_evidence: list[str] = []
    spectral_suggestions: list[str] = []
    low_mid_ratio = float(metrics["low_mid_ratio"])
    rolloff_hz = float(metrics["rolloff_hz"])
    tonal_tilt = float(metrics["tonal_tilt"])
    if low_mid_ratio > THRESHOLDS["low_mid_ratio_high"]:
        spectral_score -= (low_mid_ratio - THRESHOLDS["low_mid_ratio_high"]) * 140.0
        spectral_evidence.append(f"Low-mid energy share is {low_mid_ratio * 100:.1f}%, which may read as muddy.")
        spectral_suggestions.append("Trim 200-400 Hz congestion or rebalance overlapping instruments in that range.")
    if rolloff_hz < THRESHOLDS["rolloff_low_hz"]:
        spectral_score -= (THRESHOLDS["rolloff_low_hz"] - rolloff_hz) / 250.0
        spectral_evidence.append(f"High-frequency rolloff lands around {rolloff_hz:.0f} Hz, which can feel dark or source-limited.")
        spectral_suggestions.append("Check whether the source is bandwidth-limited or whether the master needs a gentle top-end lift.")
    if tonal_tilt > -5.0:
        spectral_score -= (tonal_tilt + 5.0) * 1.8
        spectral_evidence.append(f"Spectral tilt is {tonal_tilt:.1f}, leaning flatter or brighter than a typical full-range mix.")
        spectral_suggestions.append("Compare against a trusted reference to verify overall tonal tilt.")
    categories.append(
        _category(
            slug="spectral_balance",
            name="Spectral Balance",
            score=spectral_score,
            summary="The tonal balance is broadly even." if spectral_score >= 90.0 else "The frequency balance shows a noticeable tilt or band buildup.",
            details="Spectral balance combines low-mid density, average tilt, and high-frequency rolloff behavior.",
            evidence=spectral_evidence,
            suggestions=spectral_suggestions or ["The broadband tonal balance is within a healthy range."],
            duration_seconds=duration,
        )
    )

    low_end_score = 100.0
    low_end_evidence: list[str] = []
    low_end_suggestions: list[str] = []
    low_freq_energy_ratio = float(metrics["low_freq_energy_ratio"])
    sub_to_bass_ratio = float(metrics["sub_to_bass_ratio"])
    low_freq_side_ratio = float(metrics["low_freq_side_ratio"])
    if low_freq_energy_ratio > THRESHOLDS["low_freq_ratio_high"]:
        low_end_score -= (low_freq_energy_ratio - THRESHOLDS["low_freq_ratio_high"]) * 160.0
        low_end_evidence.append(f"Low-frequency energy share is {low_freq_energy_ratio * 100:.1f}%, which is heavy for a full-range master.")
        low_end_suggestions.append("Tighten sub and bass build-up, especially if kick and bass overlap below 100 Hz.")
    if low_freq_energy_ratio < THRESHOLDS["low_freq_ratio_low"]:
        low_end_score -= (THRESHOLDS["low_freq_ratio_low"] - low_freq_energy_ratio) * 180.0
        low_end_evidence.append(f"Low-frequency energy share is {low_freq_energy_ratio * 100:.1f}%, which may read as thin.")
        low_end_suggestions.append("Confirm the low-end translation on full-range monitors or headphones before release.")
    if sub_to_bass_ratio > THRESHOLDS["sub_to_bass_ratio_high"] or sub_to_bass_ratio < THRESHOLDS["sub_to_bass_ratio_low"]:
        low_end_score -= 12.0
        low_end_evidence.append(f"Sub-to-bass energy ratio is {sub_to_bass_ratio:.2f}, which suggests an uneven low-end distribution.")
        low_end_suggestions.append("Shape the 30-60 Hz and 60-120 Hz relationship so the low end stays anchored but readable.")
    if low_freq_side_ratio > THRESHOLDS["low_freq_side_ratio_high"]:
        low_end_score -= (low_freq_side_ratio - THRESHOLDS["low_freq_side_ratio_high"]) * 140.0
        low_end_evidence.append(f"Low-frequency side content is {low_freq_side_ratio * 100:.1f}% of the low-end energy.")
        low_end_suggestions.append("Collapse the lowest octave toward mono to improve playback consistency.")
    categories.append(
        _category(
            slug="low_end",
            name="Low-End Control",
            score=low_end_score,
            summary="The low end is proportionate and stable." if low_end_score >= 90.0 else "The low end may be too heavy, too light, or too wide.",
            details="This category looks at low-band energy share, sub-vs-bass balance, and stereo width in the lowest octave.",
            evidence=low_end_evidence,
            suggestions=low_end_suggestions or ["Low-frequency weight and focus are under control."],
            duration_seconds=duration,
        )
    )

    high_end_score = 100.0
    high_end_evidence: list[str] = []
    high_end_suggestions: list[str] = []
    presence_ratio = float(metrics["presence_ratio"])
    sibilance_ratio = float(metrics["sibilance_ratio"])
    air_ratio = float(metrics["air_ratio"])
    if presence_ratio > THRESHOLDS["presence_ratio_high"]:
        high_end_score -= (presence_ratio - THRESHOLDS["presence_ratio_high"]) * 170.0
        high_end_evidence.append(f"Presence-band energy share is {presence_ratio * 100:.1f}%, which can read as hard or fatiguing.")
        high_end_suggestions.append("Check 2-5 kHz buildup on vocals, guitars, synth leads, or cymbal edges.")
    if sibilance_ratio > THRESHOLDS["sibilance_ratio_high"]:
        high_end_score -= (sibilance_ratio - THRESHOLDS["sibilance_ratio_high"]) * 210.0
        high_end_evidence.append(f"Sibilance-band energy share is {sibilance_ratio * 100:.1f}%, raising de-essing risk.")
        high_end_suggestions.append("Revisit de-essing or dynamic EQ around 5-9 kHz.")
    if air_ratio < THRESHOLDS["air_ratio_low"]:
        high_end_score -= (THRESHOLDS["air_ratio_low"] - air_ratio) * 180.0
        high_end_evidence.append(f"Air-band energy share is {air_ratio * 100:.1f}%, which may feel closed-in.")
        high_end_suggestions.append("Verify whether the top octave needs a small, broad lift or whether the source itself is bandwidth-limited.")
    categories.append(
        _category(
            slug="high_end",
            name="High-End Harshness",
            score=high_end_score,
            summary="The upper spectrum is readable without obvious harshness." if high_end_score >= 90.0 else "The upper-mid or top-end balance may need cleanup.",
            details="High-end scoring focuses on presence, sibilance, and air-band energy balance.",
            evidence=high_end_evidence,
            suggestions=high_end_suggestions or ["Upper-frequency balance is in a workable range."],
            duration_seconds=duration,
        )
    )

    noise_score = 100.0
    noise_evidence: list[str] = []
    noise_suggestions: list[str] = []
    noise_floor_dbfs = float(metrics["noise_floor_dbfs"])
    leading_silence_sec = float(metrics["leading_silence_sec"])
    trailing_silence_sec = float(metrics["trailing_silence_sec"])
    hum_ratio = float(metrics["hum_ratio"])
    click_count = int(metrics["click_count"])
    if noise_floor_dbfs > THRESHOLDS["noise_floor_high_dbfs"]:
        noise_score -= (noise_floor_dbfs - THRESHOLDS["noise_floor_high_dbfs"]) * 1.2
        noise_evidence.append(f"The quietest windows sit around {noise_floor_dbfs:.1f} dBFS, higher than expected for a clean master.")
        noise_suggestions.append("Inspect room tone, analog chain noise, or broadband build-up in quiet passages.")
    if leading_silence_sec > THRESHOLDS["leading_silence_long"]:
        noise_score -= (leading_silence_sec - THRESHOLDS["leading_silence_long"]) * 4.0
        noise_evidence.append(f"Leading silence lasts {leading_silence_sec:.1f} seconds.")
        noise_suggestions.append("Trim the intro gap if the extra lead-in is not intentional.")
    if trailing_silence_sec > THRESHOLDS["trailing_silence_long"]:
        noise_score -= (trailing_silence_sec - THRESHOLDS["trailing_silence_long"]) * 2.5
        noise_evidence.append(f"Trailing silence lasts {trailing_silence_sec:.1f} seconds.")
        noise_suggestions.append("Shorten the tail if distribution platforms do not need the extra padding.")
    if hum_ratio > THRESHOLDS["hum_ratio_high"]:
        noise_score -= (hum_ratio - THRESHOLDS["hum_ratio_high"]) * 90.0
        noise_evidence.append(f"Low-frequency hum proxy is {hum_ratio * 100:.1f}% of sub-200 Hz energy.")
        noise_suggestions.append("Check for mains hum, resonant noise, or low-end contamination in quieter sections.")
    if click_count > THRESHOLDS["click_count_high"]:
        noise_score -= min(30.0, (click_count - THRESHOLDS["click_count_high"]) * 2.0)
        noise_evidence.append(f"Detected {click_count} sharp discontinuity candidates.")
        noise_suggestions.append("Inspect edits, fades, and restoration passes for clicks or pops.")
    categories.append(
        _category(
            slug="noise",
            name="Noise and Silence",
            score=noise_score,
            summary="Noise floor and edge silence are reasonable." if noise_score >= 90.0 else "Noise floor, silence handling, or discontinuities need review.",
            details="This category uses quiet-window RMS, edge silence duration, hum proxy, and click candidates.",
            evidence=noise_evidence,
            suggestions=noise_suggestions or ["Noise floor and silence boundaries are in a healthy range."],
            duration_seconds=duration,
        )
    )

    hygiene_score = 100.0
    hygiene_evidence: list[str] = []
    hygiene_suggestions: list[str] = []
    dc_offset = abs(float(metrics["dc_offset"]))
    if dc_offset > THRESHOLDS["dc_offset_high"]:
        hygiene_score -= (dc_offset - THRESHOLDS["dc_offset_high"]) * 1800.0
        hygiene_evidence.append(f"Detected a DC offset of {dc_offset:.4f}.")
        hygiene_suggestions.append("Remove DC offset before final limiting so low-frequency headroom is not wasted.")
    if technical_info.sample_rate < 44100:
        hygiene_score -= 8.0
        hygiene_evidence.append(f"Sample rate is {technical_info.sample_rate} Hz, lower than a common release master target.")
        hygiene_suggestions.append("Confirm that the export sample rate matches the intended release format.")
    if technical_info.bit_rate_kbps is not None and technical_info.extension == ".mp3" and technical_info.bit_rate_kbps < 192.0:
        hygiene_score -= 10.0
        hygiene_evidence.append(f"The MP3 bitrate is about {technical_info.bit_rate_kbps:.0f} kbps, which may limit top-end fidelity.")
        hygiene_suggestions.append("Prefer a lossless source or a higher MP3 bitrate for evaluation.")
    categories.append(
        _category(
            slug="technical_hygiene",
            name="Technical Hygiene",
            score=hygiene_score,
            summary="The file format and technical hygiene look acceptable." if hygiene_score >= 90.0 else "Technical housekeeping issues are visible in the file or waveform.",
            details="Technical hygiene covers DC offset, export rate, and file-level constraints like lossy source bitrate.",
            evidence=hygiene_evidence,
            suggestions=hygiene_suggestions or ["No obvious technical housekeeping issue stands out."],
            duration_seconds=duration,
        )
    )

    weighted_total = sum(category.score * WEIGHTS[category.slug] for category in categories)
    weight_sum = sum(WEIGHTS.values())
    overall_score = _clamp(weighted_total / weight_sum)

    top_issue = min(categories, key=lambda category: category.score)
    if overall_score >= 90.0:
        headline = "Technical profile is stable and release-ready."
    elif overall_score >= 75.0:
        headline = f"Overall release quality is solid, but {top_issue.name.lower()} deserves a pass before release."
    elif overall_score >= 60.0:
        headline = f"There are clear technical risks, led by {top_issue.name.lower()}."
    else:
        headline = f"The current master needs rework, especially in {top_issue.name.lower()}."

    recommendations = [_recommendation(category) for category in categories if category.severity != "info" or category.score < 95.0]
    summary = AnalysisSummary(
        overall_score=overall_score,
        risk_level=_risk_label(overall_score),
        headline=headline,
        confidence=_confidence(duration, sum(len(category.evidence) for category in categories)),
        estimated_platform_attenuation_db=float(metrics["platform_attenuation_db"]),
        top_issue=top_issue.name,
    )

    return ScoredReport(summary=summary, categories=categories, recommendations=recommendations)
