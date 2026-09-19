import os
import yaml

FM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASK = os.path.join(FM_ROOT, "task_FM", "task.yaml")
PLUGIN = os.path.join(
    FM_ROOT, "task_FM", ".praxist", "plugins",
    "panel_topologies", "fm_two_peer", "plugin.yaml",
)


def test_plugin_exists_and_rotation_matches_cohort():
    assert os.path.exists(PLUGIN)
    plugin = yaml.safe_load(open(PLUGIN, encoding="utf-8"))
    task = yaml.safe_load(open(TASK, encoding="utf-8"))
    rotation = plugin["topology"]["peer_role_rotation"]
    cohort = task["generation_policy"]["cohort_size"]
    assert cohort == 2
    assert rotation == ["exploit", "falsifier"]
    assert len(rotation) == cohort
    assert task["praxist_plugins"]["panel"]["topology"] == "panel_topology:fm_two_peer"
    assert plugin["topology"]["topology_ref"] == "panel_topology:fm_two_peer"
