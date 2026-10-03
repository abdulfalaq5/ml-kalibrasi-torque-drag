"""Lima operasi (target) yang dimodelkan dan dimensinya."""

PICK_UP = "pick_up"
SLACK_OFF = "slack_off"
ROTATING = "rotating_weight"
TORQUE_OFF = "torque_off_bottom"
TORQUE_ON = "torque_on_bottom"

OPERATIONS = [PICK_UP, SLACK_OFF, ROTATING, TORQUE_OFF, TORQUE_ON]
HOOKLOAD_OPS = [PICK_UP, SLACK_OFF, ROTATING]
TORQUE_OPS = [TORQUE_OFF, TORQUE_ON]

OP_DIMENSION = {op: "force" for op in HOOKLOAD_OPS} | {op: "torque" for op in TORQUE_OPS}

OP_LABELS = {
    PICK_UP: "Pick up",
    SLACK_OFF: "Slack off",
    ROTATING: "Rotating weight",
    TORQUE_OFF: "Torque off bottom",
    TORQUE_ON: "Torque on bottom",
}

# Skenario FF di data client: roadmap {0.1,0.3,0.5} atau {0.3,0.4,0.5}; laporan WellPlan
# {0.2,0.3,0.4,0.5}. FF 0.3 dan 0.5 ada di semua file -> dipakai sebagai fitur (K-06).
FF_SCENARIOS = [0.3, 0.5]
# Baseline WellPlan: skenario FF nominal (lihat docs/keputusan.md K-06)
BASELINE_FF = 0.3

WELL_TYPES = ["J", "S", "Horizontal"]
SECTIONS_IN = [26.0, 22.0, 17.5, 12.25, 8.5, 6.125]
