"""Export training plans as Garmin-compatible pool swim workout FIT files."""

from __future__ import annotations

import datetime
import re
import unicodedata
from typing import Any

from fit_tool.fit_file_builder import FitFileBuilder
from fit_tool.profile.messages.file_id_message import FileIdMessage
from fit_tool.profile.messages.workout_message import WorkoutMessage
from fit_tool.profile.messages.workout_step_message import WorkoutStepMessage
from fit_tool.profile.profile_type import (
    FileType,
    Intensity,
    Manufacturer,
    Sport,
    SubSport,
    WorkoutStepDuration,
    WorkoutStepTarget,
)

_PHASE_INTENSITY = {
    "热身": Intensity.WARMUP,
    "主课": Intensity.ACTIVE,
    "放松": Intensity.COOLDOWN,
}


def _sanitize_workout_name(name: str, max_len: int = 40) -> str:
    """Garmin-friendly ASCII workout name."""
    normalized = unicodedata.normalize("NFKD", name)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_name = re.sub(r"[^\w\s\-+]", "", ascii_name)
    ascii_name = re.sub(r"\s+", " ", ascii_name).strip()
    if not ascii_name:
        ascii_name = "Swim Workout"
    return ascii_name[:max_len]


_SESSION_ROMAN = {
    "恢复游": "Recovery Swim",
    "技术效率游": "Technique Swim",
    "配速稳定游": "Pace Swim",
    "间歇强化游": "Interval Swim",
    "有氧恢复 + 技术": "Aerobic Technique",
    "综合巩固游": "Consolidation Swim",
    "耐力提升游": "Endurance Swim",
}


def _session_display_name(session_type: str) -> str:
    if session_type in _SESSION_ROMAN:
        return _SESSION_ROMAN[session_type]
    return _sanitize_workout_name(session_type)


def _workout_download_name(plan: dict[str, Any]) -> str:
    session = _session_display_name(plan.get("session_type", "Swim"))
    session = session.replace(" ", "_")
    distance = plan.get("total_distance")
    if distance:
        return f"{session}_{distance}m.fit"
    return f"{session}.fit"


def _parse_rest_seconds(rest: str | None) -> float | None:
    if not rest:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)", rest)
    if not match:
        return None
    return float(match.group(1))


def _step_intensity(phase_name: str, default: Intensity = Intensity.ACTIVE) -> Intensity:
    return _PHASE_INTENSITY.get(phase_name, default)


def _step_label(phase_name: str, set_item: dict[str, Any]) -> str:
    label = (set_item.get("label") or "").strip()
    reps = set_item.get("reps", 1)
    rep_distance = set_item.get("rep_distance", 0)
    prefix = f"{reps}x{rep_distance}m" if reps > 1 else f"{rep_distance}m"
    if label:
        return f"{prefix} {label}"[:64]
    return prefix[:64]


def _apply_pace_target(step: WorkoutStepMessage, rep_distance: int, target_seconds: int | None) -> None:
    if not target_seconds or target_seconds <= 0 or rep_distance <= 0:
        step.target_type = WorkoutStepTarget.OPEN
        return

    speed_mps = rep_distance / target_seconds
    fit_speed = speed_mps * 1000.0
    step.target_type = WorkoutStepTarget.SPEED
    step.custom_target_speed_low = fit_speed * 0.97
    step.custom_target_speed_high = fit_speed * 1.03


def _add_distance_step(
    steps: list[WorkoutStepMessage],
    *,
    name: str,
    distance_m: int,
    intensity: Intensity,
    target_seconds: int | None = None,
    rep_distance: int | None = None,
    use_pace_target: bool = False,
) -> None:
    step = WorkoutStepMessage()
    step.workout_step_name = name[:64]
    step.intensity = intensity
    step.duration_type = WorkoutStepDuration.DISTANCE
    step.duration_distance = float(distance_m)
    if use_pace_target and target_seconds and rep_distance:
        _apply_pace_target(step, rep_distance, target_seconds)
    else:
        step.target_type = WorkoutStepTarget.OPEN
    steps.append(step)


def _add_rest_step(steps: list[WorkoutStepMessage], rest_seconds: float) -> None:
    step = WorkoutStepMessage()
    step.workout_step_name = f"Rest {int(rest_seconds)}s"[:64]
    step.intensity = Intensity.REST
    step.duration_type = WorkoutStepDuration.TIME
    step.duration_time = float(rest_seconds)
    step.target_type = WorkoutStepTarget.OPEN
    steps.append(step)


def _add_repeat_step(steps: list[WorkoutStepMessage], block_size: int, reps: int) -> None:
    step = WorkoutStepMessage()
    step.workout_step_name = f"Repeat {reps}x"[:64]
    step.intensity = Intensity.ACTIVE
    step.duration_type = WorkoutStepDuration.REPEAT_UNTIL_STEPS_CMPLT
    step.duration_step = block_size
    step.target_value = reps
    step.target_type = WorkoutStepTarget.OPEN
    steps.append(step)


def _append_plan_set(
    steps: list[WorkoutStepMessage],
    phase_name: str,
    set_item: dict[str, Any],
    *,
    use_pace_target: bool,
) -> None:
    reps = int(set_item.get("reps") or 1)
    rep_distance = int(set_item.get("rep_distance") or 0)
    rest_seconds = _parse_rest_seconds(set_item.get("rest"))
    target_seconds = set_item.get("target_time_per_rep")
    intensity = _step_intensity(phase_name)
    name = _step_label(phase_name, set_item)

    if reps <= 1:
        _add_distance_step(
            steps,
            name=name,
            distance_m=rep_distance,
            intensity=intensity,
            target_seconds=target_seconds,
            rep_distance=rep_distance,
            use_pace_target=use_pace_target,
        )
        return

    block_start = len(steps)
    _add_distance_step(
        steps,
        name=name,
        distance_m=rep_distance,
        intensity=intensity,
        target_seconds=target_seconds,
        rep_distance=rep_distance,
        use_pace_target=use_pace_target,
    )
    if rest_seconds:
        _add_rest_step(steps, rest_seconds)
    block_size = len(steps) - block_start
    _add_repeat_step(steps, block_size, reps)


def build_workout_fit_bytes(plan: dict[str, Any]) -> tuple[bytes, str]:
    """Build a Garmin pool swim workout FIT file from a next_plan dict."""
    if not plan or not plan.get("phases"):
        raise ValueError("训练计划为空，无法导出")

    pool_length = float(plan.get("pool_length") or 50)
    workout_name = _session_display_name(plan.get("session_type", "游泳训练"))
    steps: list[WorkoutStepMessage] = []

    for phase in plan.get("phases", []):
        phase_name = phase.get("name", "")
        use_pace_target = phase_name == "主课"
        for set_item in phase.get("sets") or []:
            _append_plan_set(steps, phase_name, set_item, use_pace_target=use_pace_target)

    if not steps:
        raise ValueError("训练计划没有可导出的训练组")

    file_id = FileIdMessage()
    file_id.type = FileType.WORKOUT
    file_id.manufacturer = Manufacturer.GARMIN.value
    file_id.product = 0
    file_id.time_created = round(datetime.datetime.now().timestamp() * 1000)
    file_id.serial_number = 0

    workout = WorkoutMessage()
    workout.workout_name = workout_name
    workout.sport = Sport.SWIMMING
    workout.sub_sport = SubSport.LAP_SWIMMING
    workout.pool_length = pool_length
    workout.num_valid_steps = len(steps)

    builder = FitFileBuilder(auto_define=True, min_string_size=64)
    builder.add(file_id)
    builder.add(workout)
    builder.add_all(steps)

    return builder.build().to_bytes(), _workout_download_name(plan)
