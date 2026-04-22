from __future__ import annotations

import math
import json
from pathlib import Path as FilePath

from models.path_model import Path, TranslationTarget
from utils.project_io import deserialize_path
from models.simulation import simulate_path


def test_simulate_path_generates_trail():
    path = Path()
    path.path_elements.append(TranslationTarget(x_meters=0.0, y_meters=0.0))
    path.path_elements.append(TranslationTarget(x_meters=3.0, y_meters=1.0))

    config = {
        "default_max_velocity_meters_per_sec": 2.0,
        "default_max_acceleration_meters_per_sec2": 4.0,
        "default_max_velocity_deg_per_sec": 90.0,
        "default_max_acceleration_deg_per_sec2": 180.0,
    }

    result = simulate_path(path, config, dt_s=0.01)

    assert result.total_time_s > 0.0
    assert result.trail_points
    assert 0.0 in result.poses_by_time


def test_simulation_does_not_spin_at_endpoint_until_guard_time():
    path_file = (
        FilePath(__file__).resolve().parents[1]
        / "tests"
        / "fixtures"
        / "top_sweep_short_depo.json"
    )
    path = deserialize_path(json.loads(path_file.read_text()))
    config = {
        "default_max_velocity_meters_per_sec": 4.5,
        "default_max_acceleration_meters_per_sec2": 12.0,
        "default_intermediate_handoff_radius_meters": 0.25,
        "default_max_velocity_deg_per_sec": 600.0,
        "default_max_acceleration_deg_per_sec2": 2000.0,
    }
    result = simulate_path(path, config, dt_s=0.02)

    end_x = 6.020539494791975
    end_y = 5.353238911495524
    reach_time = None
    for t_s in result.times_sorted:
        x_m, y_m, _theta_rad = result.poses_by_time[t_s]
        if math.hypot(x_m - end_x, y_m - end_y) <= 1e-3:
            reach_time = t_s
            break

    assert reach_time is not None
    assert result.total_time_s < 25.0
    assert result.total_time_s - reach_time <= 0.1
