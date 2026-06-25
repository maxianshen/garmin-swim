"""Parse Garmin FIT swimming activity files."""

from __future__ import annotations

import statistics
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from fitparse import FitFile

STROKE_NAMES = {
    "freestyle": "自由泳",
    "backstroke": "仰泳",
    "breaststroke": "蛙泳",
    "butterfly": "蝶泳",
    "drill": "练习",
    "mixed": "混合",
    "im": "混合泳",
}

LENGTH_TYPE_NAMES = {
    "active": "游泳",
    "rest": "休息",
    "idle": "空闲",
}

# Detect abnormally short/split pool lengths (Garmin lap-count errors).
_ABNORMAL_SWOLF_RATIO = 0.85
_ABNORMAL_TIME_RATIO = 0.88
_ABNORMAL_STROKES_RATIO = 0.82
_MERGED_SWOLF_MIN_RATIO = 0.85
_MERGED_SWOLF_MAX_RATIO = 1.25
_MERGED_TIME_MIN_RATIO = 0.85
_MERGED_TIME_MAX_RATIO = 1.25
_MERGED_STROKES_MIN_RATIO = 0.75
_MERGED_STROKES_MAX_RATIO = 1.25


def _fields_to_dict(message) -> dict[str, Any]:
    return {field.name: field.value for field in message}


def _format_stroke(stroke: str | None) -> str | None:
    if stroke is None:
        return None
    return STROKE_NAMES.get(stroke, stroke)


def _format_duration(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    total = int(seconds)
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _calc_swolf(strokes: float | None, timer_time: float | None) -> float | None:
    if strokes is None or timer_time is None:
        return None
    return round(strokes + timer_time, 1)


def _length_medians(active_lengths: list[dict[str, Any]]) -> dict[str, float]:
    swolfs = [ln["swolf"] for ln in active_lengths if ln.get("swolf") is not None]
    times = [ln["timer_time"] for ln in active_lengths if ln.get("timer_time")]
    strokes = [ln["strokes"] for ln in active_lengths if ln.get("strokes") is not None]
    return {
        "swolf": statistics.median(swolfs),
        "time": statistics.median(times),
        "strokes": statistics.median(strokes),
    }


def _is_abnormal(length: dict[str, Any], medians: dict[str, float]) -> bool:
    """A length is abnormal if any metric is clearly below the session median."""
    swolf = length.get("swolf")
    timer_time = length.get("timer_time")
    strokes = length.get("strokes")
    if swolf is None or timer_time is None or strokes is None:
        return False
    return (
        swolf < medians["swolf"] * _ABNORMAL_SWOLF_RATIO
        or timer_time < medians["time"] * _ABNORMAL_TIME_RATIO
        or strokes < medians["strokes"] * _ABNORMAL_STROKES_RATIO
    )


def _single_merge_is_valid(merged: dict[str, Any], medians: dict[str, float]) -> bool:
    """Relaxed validation when a fragment is folded into a shorter neighbor lap."""
    if _merged_is_valid(merged, medians):
        return True
    swolf = merged.get("swolf")
    timer_time = merged.get("timer_time")
    strokes = merged.get("strokes")
    if swolf is None or timer_time is None or strokes is None:
        return False
    return (
        medians["swolf"] * 0.75
        <= swolf
        <= medians["swolf"] * 1.45
        and medians["time"] * 0.75
        <= timer_time
        <= medians["time"] * 1.45
        and medians["strokes"] * 0.65
        <= strokes
        <= medians["strokes"] * 1.5
    )


def _is_consecutive_active(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return (
        a.get("length_type_raw") == "active"
        and b.get("length_type_raw") == "active"
        and b["raw_index"] == a["raw_index"] + 1
    )


def _merge_note_for(indices: list[int]) -> str:
    joined = "、".join(str(i) for i in indices)
    return f"合并自第 {joined} 趟（Garmin 记圈错误）"


def _combine_lengths(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    strokes = a["strokes"] + b["strokes"]
    timer_time = (a.get("timer_time") or 0) + (b.get("timer_time") or 0)
    elapsed_time = (a.get("elapsed_time") or 0) + (b.get("elapsed_time") or 0)

    time_a = a.get("timer_time") or 0
    time_b = b.get("timer_time") or 0
    cadence_a = a.get("avg_cadence") or 0
    cadence_b = b.get("avg_cadence") or 0
    total_time = time_a + time_b
    avg_cadence = (
        round((cadence_a * time_a + cadence_b * time_b) / total_time) if total_time else None
    )

    left = a.get("merged_from") or [a["raw_index"] + 1]
    right = b.get("merged_from") or [b["raw_index"] + 1]
    merged_from = left + right

    return {
        **a,
        "strokes": strokes,
        "timer_time": timer_time,
        "elapsed_time": elapsed_time,
        "timer_time_formatted": _format_duration(timer_time),
        "swolf": _calc_swolf(strokes, timer_time),
        "avg_cadence": avg_cadence,
        "raw_index": a["raw_index"],
        "raw_index_end": b.get("raw_index_end", b["raw_index"]),
        "merged_from": merged_from,
    }


def _merge_many_lengths(parts: list[dict[str, Any]]) -> dict[str, Any]:
    merged = _combine_lengths(parts[0], parts[1])
    for part in parts[2:]:
        merged = _combine_lengths(merged, part)
    merged_from = [part["raw_index"] + 1 for part in parts]
    merged["merged_from"] = merged_from
    merged["is_corrected"] = True
    merged["is_abnormal"] = False
    merged["merge_note"] = _merge_note_for(merged_from)
    return merged


def _build_length_to_lap(laps: list[dict[str, Any]]) -> dict[int, int]:
    """Map raw length index to lap index (0-based)."""
    mapping: dict[int, int] = {}
    for lap_i, lap in enumerate(laps):
        first_idx = lap.get("first_length_index", 0) or 0
        num_lengths = lap.get("num_lengths", 0) or 0
        for raw_i in range(first_idx, first_idx + num_lengths):
            mapping[raw_i] = lap_i
    return mapping


def _same_lap(indices: list[int], length_to_lap: dict[int, int]) -> bool:
    lap_ids = {length_to_lap[i] for i in indices if i in length_to_lap}
    return len(lap_ids) == 1


def _split_indices_by_lap(indices: list[int], length_to_lap: dict[int, int]) -> list[list[int]]:
    """Split a list of raw indices into same-lap subgroups (length >= 2 only)."""
    groups: list[list[int]] = []
    current: list[int] = []
    current_lap: int | None = None
    for idx in sorted(indices):
        lap = length_to_lap.get(idx)
        if lap is None:
            continue
        if current_lap is None or lap == current_lap:
            current.append(idx)
            current_lap = lap
        else:
            if len(current) >= 2:
                groups.append(current)
            current = [idx]
            current_lap = lap
    if len(current) >= 2:
        groups.append(current)
    return groups


def _active_neighbor_indices_in_lap(
    lengths: list[dict[str, Any]], idx: int, length_to_lap: dict[int, int]
) -> tuple[int | None, int | None]:
    lap = length_to_lap.get(idx)
    if lap is None:
        return None, None

    prev_i = next_i = None
    for j in range(idx - 1, -1, -1):
        if length_to_lap.get(j) != lap:
            break
        if lengths[j].get("length_type_raw") == "active":
            prev_i = j
            break
    for j in range(idx + 1, len(lengths)):
        if length_to_lap.get(j) != lap:
            break
        if lengths[j].get("length_type_raw") == "active":
            next_i = j
            break
    return prev_i, next_i


def _classify_abnormal(
    lengths: list[dict[str, Any]], medians: dict[str, float]
) -> tuple[list[tuple[int, int]], list[int]]:
    """Split abnormal active lengths into multi-length runs and isolated singles."""
    abnormal = [
        _is_abnormal(ln, medians) if ln.get("length_type_raw") == "active" else False
        for ln in lengths
    ]

    multi_runs: list[tuple[int, int]] = []
    singles: list[int] = []
    i = 0
    while i < len(lengths):
        if not abnormal[i]:
            i += 1
            continue

        start = i
        while i < len(lengths) and abnormal[i]:
            if i > start and not _is_consecutive_active(lengths[i - 1], lengths[i]):
                break
            i += 1

        if i - start >= 2:
            multi_runs.append((start, i))
        else:
            singles.append(start)

    return multi_runs, singles


def _pick_shorter_neighbor(
    lengths: list[dict[str, Any]],
    idx: int,
    consumed: set[int],
    length_to_lap: dict[int, int],
) -> int | None:
    prev_i, next_i = _active_neighbor_indices_in_lap(lengths, idx, length_to_lap)
    candidates: list[int] = []
    for neighbor in (prev_i, next_i):
        if neighbor is not None and neighbor not in consumed:
            candidates.append(neighbor)
    if not candidates:
        return None
    return min(candidates, key=lambda j: lengths[j].get("timer_time") or float("inf"))


def _plan_single_abnormal_merges(
    lengths: list[dict[str, Any]],
    singles: list[int],
    medians: dict[str, float],
    consumed: set[int],
    length_to_lap: dict[int, int],
) -> list[list[int]]:
    """Merge each isolated abnormal length with the shorter-time active neighbor in the same lap."""
    groups: list[list[int]] = []
    for idx in singles:
        if idx in consumed:
            continue
        if not _is_abnormal(lengths[idx], medians):
            continue
        partner = _pick_shorter_neighbor(lengths, idx, consumed, length_to_lap)
        if partner is None:
            continue
        if not _same_lap([idx, partner], length_to_lap):
            continue
        parts = sorted([lengths[idx], lengths[partner]], key=lambda ln: ln["raw_index"])
        candidate = _merge_many_lengths(parts)
        if not _single_merge_is_valid(candidate, medians):
            continue
        groups.append(sorted([idx, partner]))
        consumed.update([idx, partner])
    return groups


def _apply_length_merge_groups(
    lengths: list[dict[str, Any]],
    merge_groups: list[list[int]],
    medians: dict[str, float],
    length_to_lap: dict[int, int],
) -> tuple[dict[int, dict[str, Any]], set[int], list[dict[str, Any]]]:
    merge_at: dict[int, dict[str, Any]] = {}
    skip: set[int] = set()
    merged_groups: list[dict[str, Any]] = []

    for group in merge_groups:
        parts = [lengths[i] for i in group]
        candidate = _merge_many_lengths(parts)
        if not _single_merge_is_valid(candidate, medians):
            continue
        if not _same_lap(group, length_to_lap):
            continue
        anchor = group[0]
        merge_at[anchor] = candidate
        skip.update(group)
        both_abnormal = all(
            _is_abnormal(lengths[i], medians) for i in group if lengths[i].get("length_type_raw") == "active"
        )
        merged_groups.append(
            {
                "original_indices": candidate["merged_from"],
                "strokes": candidate["strokes"],
                "timer_time": candidate["timer_time"],
                "swolf": candidate["swolf"],
                "note": candidate["merge_note"],
                "merge_type": "multi" if both_abnormal and len(group) >= 2 else "single",
                "abnormal_indices": [
                    lengths[i]["raw_index"] + 1
                    for i in group
                    if _is_abnormal(lengths[i], medians)
                ],
            }
        )

    return merge_at, skip, merged_groups


def _merged_is_valid(merged: dict[str, Any], medians: dict[str, float]) -> bool:
    swolf = merged.get("swolf")
    timer_time = merged.get("timer_time")
    strokes = merged.get("strokes")
    if swolf is None or timer_time is None or strokes is None:
        return False
    return (
        medians["swolf"] * _MERGED_SWOLF_MIN_RATIO
        <= swolf
        <= medians["swolf"] * _MERGED_SWOLF_MAX_RATIO
        and medians["time"] * _MERGED_TIME_MIN_RATIO
        <= timer_time
        <= medians["time"] * _MERGED_TIME_MAX_RATIO
        and medians["strokes"] * _MERGED_STROKES_MIN_RATIO
        <= strokes
        <= medians["strokes"] * _MERGED_STROKES_MAX_RATIO
    )


def _correct_lengths(
    lengths: list[dict[str, Any]],
    laps: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[set[int]]]:
    """Merge abnormal active lengths into normal pool lengths (within the same lap only)."""
    if not lengths:
        return [], [], []

    for i, length in enumerate(lengths):
        length["raw_index"] = i

    length_to_lap = _build_length_to_lap(laps)

    active = [ln for ln in lengths if ln.get("length_type_raw") == "active"]
    if len(active) < 3:
        cleaned = []
        raw_index_sets = []
        for i, ln in enumerate(lengths, 1):
            item = {k: v for k, v in ln.items() if k != "raw_index"}
            item["index"] = i
            cleaned.append(item)
            raw_index_sets.append({ln["raw_index"]})
        return cleaned, [], raw_index_sets

    medians = _length_medians(active)
    multi_runs, singles = _classify_abnormal(lengths, medians)

    consumed: set[int] = set()
    merge_groups: list[list[int]] = []
    for start, end in multi_runs:
        merge_groups.extend(_split_indices_by_lap(list(range(start, end)), length_to_lap))
    for group in merge_groups:
        consumed.update(group)

    merge_groups.extend(
        _plan_single_abnormal_merges(lengths, singles, medians, consumed, length_to_lap)
    )

    merge_at, skip, merged_groups = _apply_length_merge_groups(
        lengths, merge_groups, medians, length_to_lap
    )

    output: list[dict[str, Any]] = []
    for i, length in enumerate(lengths):
        if i in skip:
            if i in merge_at:
                merged = merge_at[i]
                merged["merged_index"] = len(output) + 1
                output.append(merged)
            continue

        item = dict(length)
        if item.get("length_type_raw") == "active":
            item["is_abnormal"] = _is_abnormal(item, medians)
        output.append(item)

    cleaned: list[dict[str, Any]] = []
    raw_index_sets: list[set[int]] = []
    for length in output:
        item = {k: v for k, v in length.items() if k not in ("raw_index", "raw_index_end", "merged_index")}
        item["index"] = len(cleaned) + 1
        cleaned.append(item)
        if length.get("merged_from"):
            raw_index_sets.append({idx - 1 for idx in length["merged_from"]})
        else:
            raw_index_sets.append({length["raw_index"]})

    for group in merged_groups:
        group["merged_index"] = next(
            (
                ln["index"]
                for ln in cleaned
                if ln.get("merged_from") == group["original_indices"]
            ),
            None,
        )

    return cleaned, merged_groups, raw_index_sets


def _assign_lengths_to_laps(
    laps: list[dict[str, Any]],
    corrected_lengths: list[dict[str, Any]],
    raw_length_raw_indices: list[set[int]],
) -> list[list[dict[str, Any]]]:
    lap_length_lists: list[list[dict[str, Any]]] = [[] for _ in laps]

    for length, raw_indices in zip(corrected_lengths, raw_length_raw_indices):
        for lap_i, lap in enumerate(laps):
            first_idx = lap.get("first_length_index", 0) or 0
            num_lengths = lap.get("num_lengths", 0) or 0
            raw_range = set(range(first_idx, first_idx + num_lengths))
            if raw_indices & raw_range:
                lap_length_lists[lap_i].append(length)

    return lap_length_lists


def _summarize_active_lengths(
    active_lengths: list[dict[str, Any]], pool_length: float | None
) -> dict[str, Any]:
    if not active_lengths:
        return {
            "count": 0,
            "distance": 0,
            "strokes": 0,
            "timer_time": 0,
            "avg_swolf": None,
        }

    timer_time = sum(ln.get("timer_time") or 0 for ln in active_lengths)
    strokes = sum(ln.get("strokes") or 0 for ln in active_lengths)
    swolfs = [ln["swolf"] for ln in active_lengths if ln.get("swolf") is not None]
    distance = len(active_lengths) * (pool_length or 0)

    return {
        "count": len(active_lengths),
        "distance": distance,
        "strokes": strokes,
        "timer_time": timer_time,
        "avg_swolf": round(sum(swolfs) / len(swolfs), 1) if swolfs else None,
    }


def _parse_timestamp(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def _attach_length_heart_rates(
    lengths: list[dict[str, Any]], heart_rates: list[dict[str, Any]]
) -> None:
    if not heart_rates:
        return

    samples = [
        (_parse_timestamp(item["timestamp"]), item["heart_rate"])
        for item in heart_rates
        if item.get("timestamp") is not None and item.get("heart_rate") is not None
    ]
    if not samples:
        return

    for length in lengths:
        if length.get("length_type_raw") != "active":
            continue
        start = _parse_timestamp(length.get("start_time"))
        duration = length.get("timer_time")
        if start is None or not duration:
            continue
        start_ts = start.timestamp()
        end_ts = start_ts + duration
        in_range = [hr for ts, hr in samples if start_ts <= ts.timestamp() <= end_ts]
        if in_range:
            length["avg_heart_rate"] = round(sum(in_range) / len(in_range))
            length["max_heart_rate"] = max(in_range)


def _training_effect_label(value: float | None) -> str:
    if value is None:
        return "未知"
    if value < 1.0:
        return "轻微维持"
    if value < 2.0:
        return "基础维持"
    if value < 3.0:
        return "全面提升"
    if value < 4.0:
        return "显著提高"
    return "超量负荷"


def _build_training_analysis(
    summary: dict[str, Any],
    active_lengths: list[dict[str, Any]],
    laps: list[dict[str, Any]],
) -> dict[str, Any]:
    active_laps = [lap for lap in laps if not lap.get("is_rest")]
    swolfs = [ln["swolf"] for ln in active_lengths if ln.get("swolf") is not None]
    strokes = [ln["strokes"] for ln in active_lengths if ln.get("strokes") is not None]
    length_hrs = [ln["avg_heart_rate"] for ln in active_lengths if ln.get("avg_heart_rate")]

    fatigue_swolf_delta = None
    if len(swolfs) >= 6:
        third = max(len(swolfs) // 3, 1)
        first_avg = statistics.mean(swolfs[:third])
        last_avg = statistics.mean(swolfs[-third:])
        fatigue_swolf_delta = round(last_avg - first_avg, 1)

    hr_drift = None
    if len(length_hrs) >= 6:
        third = max(len(length_hrs) // 3, 1)
        hr_drift = round(statistics.mean(length_hrs[-third:]) - statistics.mean(length_hrs[:third]))

    stroke_std = round(statistics.stdev(strokes), 1) if len(strokes) > 1 else 0.0
    swolf_std = round(statistics.stdev(swolfs), 1) if len(swolfs) > 1 else 0.0

    training_effect = summary.get("training_effect")
    anaerobic_effect = summary.get("anaerobic_effect")
    avg_swolf = summary.get("avg_swolf")
    avg_hr = summary.get("avg_heart_rate")
    max_hr = summary.get("max_heart_rate")
    distance = summary.get("total_distance") or 0

    highlights: list[str] = []
    if training_effect is not None:
        highlights.append(
            f"有氧训练效果 {training_effect}（{_training_effect_label(training_effect)}）"
        )
    if anaerobic_effect is not None:
        highlights.append(
            f"无氧训练效果 {anaerobic_effect}（{_training_effect_label(anaerobic_effect)}）"
        )
    if avg_swolf is not None:
        highlights.append(f"平均 SWOLF {avg_swolf}，划水效率{'较好' if avg_swolf <= 80 else '有提升空间'}")
    if fatigue_swolf_delta is not None:
        if fatigue_swolf_delta > 4:
            highlights.append(f"后程 SWOLF 上升 {fatigue_swolf_delta}，后段效率下降")
        elif fatigue_swolf_delta < -2:
            highlights.append(f"后程 SWOLF 下降 {abs(fatigue_swolf_delta)}，后段越游越顺")
        else:
            highlights.append("全程 SWOLF 较稳定，配速控制良好")
    if hr_drift is not None and hr_drift > 8:
        highlights.append(f"心率后程升高约 {hr_drift} bpm，存在体能消耗累积")

    suggestions: list[str] = []
    if training_effect is not None:
        if training_effect >= 4.0:
            suggestions.append("本次有氧负荷很高，接下来 1–2 天建议轻松游或休息，避免连续高强度。")
        elif training_effect >= 3.0:
            suggestions.append("训练刺激充足，适合作为本周重点课，下次可穿插技术恢复游。")
        elif training_effect < 2.0:
            suggestions.append("整体强度偏轻，若想提升耐力，可增加 200–400 m 匀速游或缩短休息。")

    if anaerobic_effect is not None and anaerobic_effect >= 3.0:
        suggestions.append("无氧刺激明显，适合搭配划水效率练习，避免在疲劳状态下猛冲。")

    if avg_swolf is not None and avg_swolf > 85:
        suggestions.append("SWOLF 偏高：练习划距与滑行，尝试降低单趟划水次数同时保持配速。")
    elif avg_swolf is not None and avg_swolf <= 75:
        suggestions.append("划水效率不错，可尝试间歇游（如 8×50 m）巩固技术。")

    if stroke_std >= 3.5:
        suggestions.append("划水次数波动大：用节拍器或数划练习，让每趟划水更均匀。")

    if fatigue_swolf_delta is not None and fatigue_swolf_delta > 5:
        suggestions.append("后程效率下滑：分段游时控制前段配速，留体力给后半程，或增加核心力量训练。")

    if avg_hr and max_hr and max_hr - avg_hr > 25:
        suggestions.append("最高心率明显高于平均，高强度趟较多，注意充分热身与放松。")

    if distance >= 2000 and training_effect is not None and training_effect < 3.0:
        suggestions.append("长距离游泳但训练效果中等，可尝试变化配速（快慢交替）提高刺激。")

    if not suggestions:
        suggestions.append("保持当前训练节奏，定期记录 SWOLF 与心率变化以跟踪进步。")

    analysis = {
        "training_effect": training_effect,
        "training_effect_label": _training_effect_label(training_effect),
        "anaerobic_effect": anaerobic_effect,
        "anaerobic_effect_label": _training_effect_label(anaerobic_effect),
        "fatigue_swolf_delta": fatigue_swolf_delta,
        "heart_rate_drift": hr_drift,
        "stroke_consistency": stroke_std,
        "swolf_consistency": swolf_std,
        "active_lap_count": len(active_laps),
        "highlights": highlights,
        "suggestions": suggestions,
    }
    analysis["next_plan"] = _build_next_training_plan(summary, analysis)
    return analysis


def _round_distance(distance: float, pool_length: float) -> int:
    if not pool_length:
        return int(round(distance / 50) * 50)
    return int(round(distance / pool_length) * pool_length)


def _pace_for_intensity(pace_100: float | None, intensity: str, mode: str = "normal") -> float:
    """Estimate seconds per 100 m for a given intensity mode."""
    base = pace_100 or 110.0
    factors = {
        "easy": 1.14,
        "normal": 1.0,
        "steady": 1.04,
        "moderate": 1.0,
        "fast": 0.92,
        "recovery": 1.12,
    }
    if intensity in ("低", "低中") and mode == "normal":
        mode = "easy"
    elif intensity == "中高" and mode == "normal":
        mode = "fast"
    return base * factors.get(mode, 1.0)


def _target_time_seconds(distance_m: float, pace_100: float | None, intensity: str, mode: str = "normal") -> int:
    pace = _pace_for_intensity(pace_100, intensity, mode)
    return max(1, round(pace * (distance_m / 100)))


def _plan_set(
    label: str,
    reps: int,
    rep_distance: int,
    *,
    pace_100: float | None,
    intensity: str,
    mode: str = "normal",
    rest: str | None = None,
) -> dict[str, Any]:
    per_rep = _target_time_seconds(rep_distance, pace_100, intensity, mode)
    total = per_rep * reps
    return {
        "label": label,
        "reps": reps,
        "rep_distance": rep_distance,
        "distance": reps * rep_distance,
        "rest": rest,
        "target_time_per_rep": per_rep,
        "target_time_per_rep_formatted": _format_duration(per_rep),
        "target_time_total": total,
        "target_time_total_formatted": _format_duration(total),
        "description": (
            f"{reps}×{rep_distance} m {label}，"
            f"每组目标 {_format_duration(per_rep)}，"
            f"合计约 {_format_duration(total)}"
            + (f"，休 {rest}" if rest else "")
        ),
    }


def _phase_sets_to_items(sets: list[dict[str, Any]]) -> list[str]:
    return [s["description"] for s in sets]


def _build_next_training_plan(
    summary: dict[str, Any], analysis: dict[str, Any]
) -> dict[str, Any]:
    pool = summary.get("pool_length") or 50
    last_distance = summary.get("total_distance") or 1500
    avg_swolf = summary.get("avg_swolf")
    avg_hr = summary.get("avg_heart_rate")
    pace_100 = summary.get("avg_pace_per_100m")
    te = analysis.get("training_effect")
    ae = analysis.get("anaerobic_effect")
    fatigue = analysis.get("fatigue_swolf_delta")
    hr_drift = analysis.get("heart_rate_drift")
    stroke_std = analysis.get("stroke_consistency") or 0

    # Session archetype
    if te is not None and te >= 4.0:
        session_type = "恢复游"
        focus = "主动恢复、技术放松"
        rest_days = 1
        distance_factor = 0.55
        intensity = "低"
    elif te is not None and te >= 3.0:
        if fatigue is not None and fatigue > 5:
            session_type = "配速稳定游"
            focus = "后程不掉速、SWOLF 控制"
            rest_days = 1
            distance_factor = 0.85
            intensity = "中"
        elif avg_swolf is not None and avg_swolf > 85:
            session_type = "技术效率游"
            focus = "降划水、拉长划距"
            rest_days = 1
            distance_factor = 0.75
            intensity = "低中"
        elif (
            ae is not None
            and ae >= 2.5
            and avg_swolf is not None
            and avg_swolf <= 76
            and (fatigue or 0) <= 3
        ):
            session_type = "间歇强化游"
            focus = "速度耐力、心率间歇"
            rest_days = 1
            distance_factor = 0.9
            intensity = "中高"
        else:
            session_type = "综合巩固游"
            focus = "技术 + 匀速耐力"
            rest_days = 1
            distance_factor = 0.9
            intensity = "中"
    elif te is not None and te < 2.0:
        session_type = "耐力提升游"
        focus = "增加距离与有氧刺激"
        rest_days = 0
        distance_factor = 1.1
        intensity = "中"
    elif avg_swolf is not None and avg_swolf > 85:
        session_type = "技术效率游"
        focus = "降划水、拉长划距"
        rest_days = 1
        distance_factor = 0.75
        intensity = "低中"
    else:
        session_type = "综合巩固游"
        focus = "技术 + 匀速耐力"
        rest_days = 1
        distance_factor = 0.9
        intensity = "中"

    if ae is not None and ae >= 3.0 and session_type in ("间歇强化游", "综合巩固游"):
        session_type = "有氧恢复 + 技术"
        focus = "无氧负荷后转化，稳 SWOLF"
        intensity = "低中"
        distance_factor = 0.8

    total_distance = _round_distance(last_distance * distance_factor, pool)
    total_distance = max(pool * 8, min(total_distance, int(last_distance * 1.15)))

    target_swolf = None
    if avg_swolf is not None:
        if session_type in ("技术效率游", "恢复游"):
            target_swolf = f"≤{round(avg_swolf - 3)}"
        elif session_type == "配速稳定游":
            target_swolf = f"全程波动 < 5（参考 {round(avg_swolf)}）"
        else:
            target_swolf = f"{round(avg_swolf - 2)}–{round(avg_swolf + 2)}"

    target_hr = None
    if avg_hr:
        if intensity in ("低", "低中"):
            target_hr = f"{max(100, avg_hr - 15)}–{avg_hr - 5} bpm"
        elif intensity == "中高":
            target_hr = f"{avg_hr - 5}–{avg_hr + 12} bpm"
        else:
            target_hr = f"{avg_hr - 8}–{avg_hr + 5} bpm"

    target_pace = None
    if pace_100 and session_type == "间歇强化游":
        target_pace = f"快组 ~{round(pace_100 - 5)} s/100m，慢组 ~{round(pace_100 + 8)} s/100m"
    elif pace_100:
        target_pace = f"匀速 ~{round(pace_100)}–{round(pace_100 + 5)} s/100m"

    warmup_dist = _round_distance(min(400, total_distance * 0.2), pool)
    cooldown_dist = _round_distance(min(200, total_distance * 0.12), pool)
    main_dist = total_distance - warmup_dist - cooldown_dist

    pool_i = int(pool)
    phases: list[dict[str, Any]] = []

    warmup_sets = [
        _plan_set(
            "轻松自由泳",
            1,
            warmup_dist,
            pace_100=pace_100,
            intensity=intensity,
            mode="easy",
        ),
        _plan_set(
            "划一换气 / 侧身打腿",
            4,
            pool_i,
            pace_100=pace_100,
            intensity=intensity,
            mode="easy",
            rest="15 s",
        ),
    ]
    phases.append(
        {
            "name": "热身",
            "distance": warmup_dist,
            "sets": warmup_sets,
            "items": _phase_sets_to_items(warmup_sets),
        }
    )

    main_sets: list[dict[str, Any]] = []
    if session_type == "恢复游":
        main_sets = [
            _plan_set(
                "连续轻松游",
                1,
                main_dist,
                pace_100=pace_100,
                intensity="低",
                mode="easy",
            ),
        ]
    elif session_type == "技术效率游":
        rep_dist = pool_i * 2
        reps = max(4, main_dist // rep_dist)
        main_sets = [
            _plan_set(
                "划距练习（去程注意划距，回程正常）",
                reps,
                rep_dist,
                pace_100=pace_100,
                intensity=intensity,
                mode="steady",
                rest="20 s",
            ),
            _plan_set(
                "手夹板划水（如有装备）",
                4,
                pool_i,
                pace_100=pace_100,
                intensity=intensity,
                mode="steady",
                rest="20 s",
            ),
        ]
    elif session_type == "配速稳定游":
        rep_dist = pool_i * 4
        chunks = max(3, main_dist // rep_dist)
        main_sets = [
            _plan_set(
                "匀速游",
                chunks,
                rep_dist,
                pace_100=pace_100,
                intensity=intensity,
                mode="moderate",
                rest="30 s",
            ),
        ]
    elif session_type == "间歇强化游":
        fast_rep = pool_i * 2
        n = max(6, main_dist // (fast_rep * 2))
        main_sets = [
            _plan_set(
                "快速组（RPE 7–8）",
                n,
                fast_rep,
                pace_100=pace_100,
                intensity="中高",
                mode="fast",
                rest="25 s",
            ),
            _plan_set(
                "轻松恢复游",
                max(4, n // 2),
                fast_rep,
                pace_100=pace_100,
                intensity="中高",
                mode="recovery",
                rest="20 s",
            ),
        ]
    elif session_type == "有氧恢复 + 技术":
        rep_dist = pool_i * 4
        reps = max(4, main_dist // rep_dist)
        main_sets = [
            _plan_set(
                "轻松匀速",
                reps,
                rep_dist,
                pace_100=pace_100,
                intensity="低中",
                mode="steady",
                rest="30 s",
            ),
            _plan_set(
                "最后冲刺（略提速，不全力）",
                2,
                pool_i,
                pace_100=pace_100,
                intensity="低中",
                mode="moderate",
                rest="30 s",
            ),
        ]
    elif session_type == "耐力提升游":
        main_sets = [
            _plan_set(
                "连续耐力游",
                1,
                main_dist,
                pace_100=pace_100,
                intensity=intensity,
                mode="moderate",
            ),
        ]
    else:
        rep_dist = pool_i * 4
        sets_count = max(4, main_dist // rep_dist)
        main_sets = [
            _plan_set(
                "自由泳（偶数趟控制划频）",
                sets_count,
                rep_dist,
                pace_100=pace_100,
                intensity=intensity,
                mode="moderate",
                rest="25 s",
            ),
        ]

    phases.append(
        {
            "name": "主课",
            "distance": main_dist,
            "sets": main_sets,
            "items": _phase_sets_to_items(main_sets),
        }
    )

    cooldown_sets = [
        _plan_set(
            "超轻松仰泳 / 自由泳",
            1,
            cooldown_dist,
            pace_100=pace_100,
            intensity="低",
            mode="easy",
        ),
    ]
    phases.append(
        {
            "name": "放松",
            "distance": cooldown_dist,
            "sets": cooldown_sets,
            "items": _phase_sets_to_items(cooldown_sets),
        }
    )

    total_target_time = sum(
        s["target_time_total"] for phase in phases for s in phase.get("sets", [])
    )

    rationale_parts = []
    if te is not None:
        rationale_parts.append(f"本次有氧效果 {te}（{analysis.get('training_effect_label')}）")
    if avg_swolf is not None:
        rationale_parts.append(f"平均 SWOLF {avg_swolf}")
    if fatigue is not None and fatigue > 4:
        rationale_parts.append(f"后程 SWOLF 升 {fatigue}")
    rationale = "，".join(rationale_parts) + f" → 建议下次进行「{session_type}」。"

    schedule_note = (
        f"建议休息 {rest_days} 天后训练"
        if rest_days
        else "若身体恢复良好，可隔日进行"
    )

    return {
        "session_type": session_type,
        "focus": focus,
        "intensity": intensity,
        "rest_days_before": rest_days,
        "schedule_note": schedule_note,
        "total_distance": total_distance,
        "pool_length": pool,
        "target_swolf": target_swolf,
        "target_heart_rate": target_hr,
        "target_pace": target_pace,
        "target_time_total": total_target_time,
        "target_time_total_formatted": _format_duration(total_target_time),
        "phases": phases,
        "rationale": rationale,
    }


def parse_swim_fit(path: str | Path) -> dict[str, Any]:
    """Parse a Garmin FIT swimming file and return structured activity data."""
    fitfile = FitFile(str(path))

    session = None
    activity = None
    laps: list[dict] = []
    lengths: list[dict] = []
    heart_rates: list[dict] = []

    for message in fitfile.messages:
        if message.name == "session" and session is None:
            session = _fields_to_dict(message)
        elif message.name == "activity" and activity is None:
            activity = _fields_to_dict(message)
        elif message.name == "lap":
            laps.append(_fields_to_dict(message))
        elif message.name == "length":
            lengths.append(_fields_to_dict(message))
        elif message.name == "record":
            fields = _fields_to_dict(message)
            if "heart_rate" in fields and "timestamp" in fields:
                heart_rates.append(
                    {
                        "timestamp": _iso(fields["timestamp"]),
                        "heart_rate": fields["heart_rate"],
                    }
                )

    if not session:
        raise ValueError("No session data found in FIT file")

    pool_length = session.get("pool_length")
    pool_unit = session.get("pool_length_unit", "metric")
    total_distance = session.get("total_distance", 0)
    total_timer = session.get("total_timer_time", 0)
    avg_speed = session.get("enhanced_avg_speed") or session.get("avg_speed")

    parsed_lengths_raw = []
    for i, length in enumerate(lengths):
        timer_time = length.get("total_timer_time")
        strokes = length.get("total_strokes", 0)
        parsed_lengths_raw.append(
            {
                "index": i + 1,
                "stroke": _format_stroke(length.get("swim_stroke")),
                "stroke_raw": length.get("swim_stroke"),
                "length_type": LENGTH_TYPE_NAMES.get(
                    length.get("length_type"), length.get("length_type")
                ),
                "length_type_raw": length.get("length_type"),
                "elapsed_time": length.get("total_elapsed_time"),
                "timer_time": timer_time,
                "timer_time_formatted": _format_duration(timer_time),
                "strokes": strokes,
                "swolf": _calc_swolf(strokes, timer_time),
                "avg_cadence": length.get("avg_swimming_cadence"),
                "avg_speed": length.get("avg_speed"),
                "start_time": _iso(length.get("start_time")),
            }
        )

    parsed_lengths, merge_corrections, raw_index_sets = _correct_lengths(parsed_lengths_raw, laps)
    _attach_length_heart_rates(parsed_lengths, heart_rates)
    lap_length_lists = _assign_lengths_to_laps(laps, parsed_lengths, raw_index_sets)

    raw_active = [ln for ln in parsed_lengths_raw if ln.get("length_type_raw") == "active"]
    raw_medians = _length_medians(raw_active) if raw_active else None
    if raw_medians:
        for ln in parsed_lengths_raw:
            if ln.get("length_type_raw") == "active":
                ln["is_abnormal"] = _is_abnormal(ln, raw_medians)

    corrected_active = [ln for ln in parsed_lengths if ln.get("length_type_raw") == "active"]
    raw_summary = _summarize_active_lengths(raw_active, pool_length)
    corrected_summary = _summarize_active_lengths(corrected_active, pool_length)

    parsed_laps = []
    for i, lap in enumerate(laps):
        lap_lengths = lap_length_lists[i]
        active_lengths = [
            ln for ln in lap_lengths if ln.get("length_type_raw") == "active"
        ]
        lap_stats = _summarize_active_lengths(active_lengths, pool_length)

        parsed_laps.append(
            {
                "index": i + 1,
                "stroke": _format_stroke(lap.get("swim_stroke")),
                "stroke_raw": lap.get("swim_stroke"),
                "distance": 0 if lap.get("total_distance", 0) == 0 else lap_stats["distance"],
                "distance_raw": lap.get("total_distance", 0),
                "elapsed_time": lap.get("total_elapsed_time"),
                "timer_time": lap_stats["timer_time"] if active_lengths else lap.get("total_timer_time"),
                "timer_time_formatted": _format_duration(
                    lap_stats["timer_time"] if active_lengths else lap.get("total_timer_time")
                ),
                "strokes": lap_stats["strokes"] if active_lengths else lap.get("total_cycles", 0),
                "avg_swolf": lap_stats["avg_swolf"],
                "avg_heart_rate": lap.get("avg_heart_rate"),
                "max_heart_rate": lap.get("max_heart_rate"),
                "avg_cadence": lap.get("avg_cadence"),
                "avg_speed": lap.get("enhanced_avg_speed") or lap.get("avg_speed"),
                "num_lengths": len(lap_lengths),
                "num_lengths_raw": lap.get("num_lengths"),
                "is_rest": lap.get("total_distance", 0) == 0,
                "lengths": lap_lengths,
            }
        )

    active_laps = [lap for lap in parsed_laps if not lap["is_rest"]]
    rest_laps = [lap for lap in parsed_laps if lap["is_rest"]]

    corrected_avg_speed = (
        corrected_summary["distance"] / corrected_summary["timer_time"]
        if corrected_summary["timer_time"]
        else avg_speed
    )

    training_analysis = _build_training_analysis(
        {
            "training_effect": session.get("total_training_effect"),
            "anaerobic_effect": session.get("total_anaerobic_training_effect"),
            "avg_swolf": corrected_summary["avg_swolf"],
            "avg_heart_rate": session.get("avg_heart_rate"),
            "max_heart_rate": session.get("max_heart_rate"),
            "total_distance": corrected_summary["distance"],
        },
        corrected_active,
        parsed_laps,
    )

    return {
        "summary": {
            "sport": session.get("sport"),
            "sub_sport": session.get("sub_sport"),
            "start_time": _iso(session.get("start_time")),
            "end_time": _iso(session.get("timestamp")),
            "pool_length": pool_length,
            "pool_length_unit": pool_unit,
            "total_distance": corrected_summary["distance"],
            "total_distance_raw": total_distance,
            "total_elapsed_time": session.get("total_elapsed_time"),
            "total_timer_time": total_timer,
            "total_elapsed_formatted": _format_duration(session.get("total_elapsed_time")),
            "total_timer_formatted": _format_duration(total_timer),
            "total_calories": session.get("total_calories"),
            "total_strokes": corrected_summary["strokes"],
            "total_strokes_raw": session.get("total_cycles"),
            "num_laps": session.get("num_laps"),
            "num_active_lengths": corrected_summary["count"],
            "num_active_lengths_raw": session.get("num_active_lengths"),
            "avg_swolf": corrected_summary["avg_swolf"],
            "avg_swolf_raw": raw_summary["avg_swolf"],
            "avg_heart_rate": session.get("avg_heart_rate"),
            "max_heart_rate": session.get("max_heart_rate"),
            "avg_cadence": session.get("avg_cadence"),
            "avg_speed": corrected_avg_speed,
            "avg_pace_per_100m": round(100 / corrected_avg_speed, 1) if corrected_avg_speed else None,
            "training_effect": session.get("total_training_effect"),
            "anaerobic_effect": session.get("total_anaerobic_training_effect"),
            "activity_type": activity.get("type") if activity else None,
        },
        "laps": parsed_laps,
        "lengths": parsed_lengths,
        "lengths_raw": parsed_lengths_raw,
        "corrections": {
            "merged_groups": merge_corrections,
            "merge_count": len(merge_corrections),
            "distance_delta": corrected_summary["distance"] - raw_summary["distance"],
            "length_count_delta": corrected_summary["count"] - raw_summary["count"],
            "abnormal_indices_raw": [
                ln["index"]
                for ln in parsed_lengths_raw
                if ln.get("length_type_raw") == "active"
                and _is_abnormal(ln, _length_medians(raw_active))
            ]
            if raw_active
            else [],
        },
        "stats": {
            "active_lap_count": len(active_laps),
            "rest_lap_count": len(rest_laps),
            "active_distance": sum(lap["distance"] for lap in active_laps),
            "active_distance_raw": sum(lap["distance_raw"] for lap in active_laps),
            "length_count": len(parsed_lengths),
            "length_count_raw": len(parsed_lengths_raw),
        },
        "heart_rate_series": heart_rates,
        "training_analysis": training_analysis,
    }


def list_fit_files(directory: str | Path) -> list[Path]:
    """Return .fit files in directory, newest first by modification time."""
    root = Path(directory)
    if not root.is_dir():
        return []
    files = [p for p in root.iterdir() if p.is_file() and p.suffix.lower() == ".fit"]
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


def _directory_signature(directory: str | Path) -> tuple[str, float, int]:
    root = Path(directory).resolve()
    files = list_fit_files(root)
    modified_total = sum(path.stat().st_mtime for path in files)
    return str(root), modified_total, len(files)


_CALENDAR_CACHE: dict[tuple[str, float, int], list[dict[str, Any]]] = {}


def activity_list_item(path: Path, data: dict[str, Any]) -> dict[str, Any]:
    summary = data["summary"]
    corrections = data.get("corrections", {})
    return {
        "filename": path.name,
        "start_time": summary.get("start_time"),
        "sport": summary.get("sport"),
        "sub_sport": summary.get("sub_sport"),
        "total_distance": summary.get("total_distance"),
        "total_distance_raw": summary.get("total_distance_raw"),
        "total_timer_formatted": summary.get("total_timer_formatted"),
        "total_calories": summary.get("total_calories"),
        "avg_swolf": summary.get("avg_swolf"),
        "avg_heart_rate": summary.get("avg_heart_rate"),
        "num_active_lengths": summary.get("num_active_lengths"),
        "merge_count": corrections.get("merge_count", 0),
        "file_size": path.stat().st_size,
        "modified_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
    }


def list_swim_activities(directory: str | Path) -> list[dict[str, Any]]:
    """Scan directory and return summary for each swim FIT file."""
    items: list[dict[str, Any]] = []
    for path in list_fit_files(directory):
        try:
            data = parse_swim_fit(path)
            if data["summary"].get("sport") != "swimming":
                continue
            items.append(activity_list_item(path, data))
        except Exception as exc:
            items.append(
                {
                    "filename": path.name,
                    "error": str(exc),
                    "modified_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
                }
            )

    items.sort(key=lambda item: item.get("start_time") or item.get("modified_at") or "", reverse=True)
    return items


def _planned_training_date(start_time: str | None, rest_days: int | None) -> str | None:
    activity_dt = _parse_timestamp(start_time)
    if not activity_dt:
        return None
    offset = rest_days if rest_days and rest_days > 0 else 1
    return (activity_dt.date() + timedelta(days=offset)).isoformat()


def build_calendar_events(directory: str | Path) -> list[dict[str, Any]]:
    """Build calendar events from completed swims and suggested next sessions."""
    cache_key = _directory_signature(directory)
    cached = _CALENDAR_CACHE.get(cache_key)
    if cached is not None:
        return cached

    events: list[dict[str, Any]] = []
    for path in list_fit_files(directory):
        try:
            data = parse_swim_fit(path)
            if data["summary"].get("sport") != "swimming":
                continue

            summary = data["summary"]
            start_time = summary.get("start_time")
            activity_date = start_time[:10] if start_time else None

            if activity_date:
                events.append(
                    {
                        "id": f"completed:{path.name}",
                        "type": "completed",
                        "date": activity_date,
                        "start_time": start_time,
                        "filename": path.name,
                        "title": path.stem,
                        "total_distance": summary.get("total_distance"),
                        "total_timer_formatted": summary.get("total_timer_formatted"),
                        "avg_swolf": summary.get("avg_swolf"),
                        "avg_heart_rate": summary.get("avg_heart_rate"),
                        "training_effect": summary.get("training_effect"),
                    }
                )

            plan = (data.get("training_analysis") or {}).get("next_plan")
            planned_date = _planned_training_date(
                start_time, plan.get("rest_days_before") if plan else None
            )
            if plan and planned_date:
                events.append(
                    {
                        "id": f"planned:{path.name}",
                        "type": "planned",
                        "date": planned_date,
                        "filename": path.name,
                        "source_filename": path.name,
                        "source_date": activity_date,
                        "title": plan.get("session_type"),
                        "session_type": plan.get("session_type"),
                        "total_distance": plan.get("total_distance"),
                        "intensity": plan.get("intensity"),
                        "focus": plan.get("focus"),
                        "target_time_total_formatted": plan.get("target_time_total_formatted"),
                        "schedule_note": plan.get("schedule_note"),
                        "rest_days_before": plan.get("rest_days_before"),
                    }
                )
        except Exception:
            continue

    events.sort(key=lambda item: (item["date"], item["type"] != "completed"))
    _CALENDAR_CACHE[cache_key] = events
    return events
