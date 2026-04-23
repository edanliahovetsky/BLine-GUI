from __future__ import annotations

from ui.sidebar.sidebar import Sidebar
from ui.sidebar.widgets.segment_bar import SegmentBar
from utils.project_io import deserialize_path


def _top_sweep_short_first_like_data() -> dict:
    """Representative path that previously produced a duplicated first SegmentBar."""
    return {
        "path_elements": [
            {
                "type": "waypoint",
                "translation_target": {
                    "x_meters": 3.3618357031090778,
                    "y_meters": 5.467912742167626,
                    "intermediate_handoff_radius_meters": 0.55,
                },
                "rotation_target": {
                    "rotation_radians": 0.0,
                    "profiled_rotation": True,
                },
            },
            {"type": "event_trigger", "t_ratio": 0.0, "lib_key": "intake"},
            {"type": "event_trigger", "t_ratio": 0.027072700747227063, "lib_key": "ready"},
            {
                "type": "rotation",
                "rotation_radians": 0.0,
                "t_ratio": 0.11819898491917201,
                "profiled_rotation": True,
            },
            {
                "type": "waypoint",
                "translation_target": {
                    "x_meters": 5.522696506757095,
                    "y_meters": 5.46504577032045,
                    "intermediate_handoff_radius_meters": 0.3,
                },
                "rotation_target": {
                    "rotation_radians": 0.0,
                    "profiled_rotation": True,
                },
            },
            {
                "type": "translation",
                "x_meters": 6.635664509399378,
                "y_meters": 6.7678376634560635,
                "intermediate_handoff_radius_meters": 0.4,
            },
            {
                "type": "rotation",
                "rotation_radians": -0.832796013884693,
                "t_ratio": 0.42938011338921184,
                "profiled_rotation": True,
            },
            {
                "type": "translation",
                "x_meters": 7.727253095855749,
                "y_meters": 6.655499013729224,
                "intermediate_handoff_radius_meters": 0.5,
            },
            {
                "type": "translation",
                "x_meters": 7.77063539109338,
                "y_meters": 6.052332312318486,
                "intermediate_handoff_radius_meters": 0.35,
            },
            {
                "type": "rotation",
                "rotation_radians": -1.6709863640804155,
                "t_ratio": 0.0,
                "profiled_rotation": True,
            },
            {
                "type": "translation",
                "x_meters": 7.743381538826155,
                "y_meters": 5.296494616235524,
                "intermediate_handoff_radius_meters": 0.35,
            },
            {
                "type": "rotation",
                "rotation_radians": -2.515375257072157,
                "t_ratio": 0.5424280516202081,
                "profiled_rotation": True,
            },
            {
                "type": "translation",
                "x_meters": 7.207799716998004,
                "y_meters": 4.732465845173137,
                "intermediate_handoff_radius_meters": 0.35,
            },
            {
                "type": "translation",
                "x_meters": 6.426150384770895,
                "y_meters": 4.706043480662472,
                "intermediate_handoff_radius_meters": 0.35,
            },
            {
                "type": "rotation",
                "rotation_radians": 2.338365721278719,
                "t_ratio": 0.22171551565660735,
                "profiled_rotation": True,
            },
            {
                "type": "translation",
                "x_meters": 5.5112094515786225,
                "y_meters": 5.41769705632308,
                "intermediate_handoff_radius_meters": 0.35,
            },
            {"type": "event_trigger", "t_ratio": 0.25004449679899454, "lib_key": "shoot"},
            {
                "type": "rotation",
                "rotation_radians": -3.1412408946364416,
                "t_ratio": 0.3825690749687212,
                "profiled_rotation": True,
            },
            {"type": "event_trigger", "t_ratio": 0.8532847311565571, "lib_key": "alt"},
            {
                "type": "waypoint",
                "translation_target": {
                    "x_meters": 3.3147714219231617,
                    "y_meters": 5.380198495475318,
                    "intermediate_handoff_radius_meters": 0.45,
                },
                "rotation_target": {
                    "rotation_radians": 2.6423351524405727,
                    "profiled_rotation": True,
                },
            },
        ],
        "constraints": {
            "max_velocity_meters_per_sec": [
                {"value": 2.0, "start_ordinal": 0, "end_ordinal": 1},
                {"value": 4.0, "start_ordinal": 2, "end_ordinal": 2},
                {"value": 3.5, "start_ordinal": 3, "end_ordinal": 4},
                {"value": 3.5, "start_ordinal": 5, "end_ordinal": 7},
                {"value": 2.2, "start_ordinal": 8, "end_ordinal": 8},
                {"value": 2.0, "start_ordinal": 9, "end_ordinal": 9},
            ]
        },
    }


def test_sidebar_reselection_does_not_leave_duplicate_segment_bars(qt_app):
    path = deserialize_path(_top_sweep_short_first_like_data())
    sidebar = Sidebar(path)
    sidebar.show()

    sidebar.select_index(0, defer=False)
    qt_app.processEvents()
    assert len(sidebar.findChildren(SegmentBar)) == 1
    spinbox = sidebar.constraint_manager._segment_spinboxes["max_velocity_meters_per_sec"]
    assert spinbox.isVisible()

    sidebar.refresh_current_selection()
    assert len(sidebar.findChildren(SegmentBar)) == 1
    assert spinbox.isVisible()

    qt_app.processEvents()
    assert len(sidebar.findChildren(SegmentBar)) == 1
    assert spinbox.isVisible()

    sidebar.close()
