"""只读计数。返回字典，不对照账本，也不决定退出码。"""
import argparse
import glob
import json
import os
import sys

RUN_IDS = (
    "run_2026-11-17_01-55-15_primary_task_FM",
    "run_2026-11-17_03-55-34_primary_task_FM",
    "run_2026-11-17_05-56-23_primary_task_FM",
    "run_2026-11-17_07-56-25_primary_task_FM",
    "run_2026-11-17_10-57-34_primary_task_FM",
    "run_2026-11-17_13-50-15_primary_task_FM",
    "run_2026-11-17_16-05-58_primary_task_FM",
    "run_2026-11-17_18-07-01_primary_task_FM",
    "run_2026-11-18_00-28-23_primary_task_FM",
    "run_2026-11-18_02-25-52_primary_task_FM",
    "run_2026-11-18_04-23-37_primary_task_FM",
    "run_2026-11-18_06-22-12_primary_task_FM",
    "run_2026-11-18_08-38-47_primary_task_FM",
    "run_2026-11-18_10-41-10_primary_task_FM",
    "run_2026-11-18_12-41-11_primary_task_FM",
)

_SCHEMA = "fm.hypothesis_proposal.v1"
_FP_PREFIX = "f02b2a43"
_PRESCREEN_SUFFIX = ".prescreen.json"
_DONE_MARKERS = ("2026-11-17", "2026-11-18")


def _read_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def census(root):
    root = os.fspath(root)
    proposal_json_excluding_prescreen = 0
    hypothesis_v1 = 0
    unparseable_proposal_json = 0
    prescreen_files = 0
    prescreen_good = True
    runs = []
    allowed = set(RUN_IDS)
    for run_id in RUN_IDS:
        run_dir = os.path.join(root, "task_FM", "experiments", run_id)
        count = 0
        if os.path.isdir(run_dir):
            pattern = os.path.join(run_dir, "results", "**", "proposals", "*.json")
            for path in glob.glob(pattern, recursive=True):
                if os.path.basename(path).endswith(_PRESCREEN_SUFFIX):
                    prescreen_files += 1
                    try:
                        body = _read_json(path)
                    except json.JSONDecodeError:
                        prescreen_good = False
                    else:
                        if not (
                            isinstance(body, dict)
                            and body.get("status") == "degraded"
                            and body.get("note") == "TypeSafe API 超时"
                        ):
                            prescreen_good = False
                    continue
                count += 1
                proposal_json_excluding_prescreen += 1
                try:
                    body = _read_json(path)
                except json.JSONDecodeError:
                    unparseable_proposal_json += 1
                    continue
                if isinstance(body, dict) and body.get("schema") == _SCHEMA:
                    hypothesis_v1 += 1
        runs.append({
            "id": run_id,
            "proposal_json_excluding_prescreen": count,
        })
    zero_rows = _zero_rows(os.path.join(
        root, "task_FM", "config", "aligned_verdicts.jsonl"))
    enqueued, src_hits = _done_counts(os.path.join(
        root, "data", "cache", "aligned_pending.done.jsonl"), allowed)
    return {
        "direction_field": "dir_acc",
        "dir_acc_zero_rows_current_ok": zero_rows,
        "hypothesis_v1": hypothesis_v1,
        "unparseable_proposal_json": unparseable_proposal_json,
        "proposal_json_excluding_prescreen": proposal_json_excluding_prescreen,
        "prescreen_files": prescreen_files,
        "prescreen_all_degraded_timeout": prescreen_files > 0 and prescreen_good,
        "done_enqueued_at_on_2026_11_17_or_18": enqueued,
        "done_src_run_in_window": src_hits,
        "runs": runs,
    }


def _zero_rows(path):
    if not os.path.isfile(path):
        return 0
    count = 0
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                row = json.loads(text)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict) or row.get("status") != "ok":
                continue
            fingerprint = row.get("protocol_fingerprint")
            if not isinstance(fingerprint, str) or not fingerprint.startswith(_FP_PREFIX):
                continue
            value = row.get("dir_acc")
            if (
                not isinstance(value, bool)
                and isinstance(value, (int, float))
                and value == 0
            ):
                count += 1
    return count


def _done_counts(path, allowed):
    enqueued = 0
    src_hits = 0
    if not os.path.isfile(path):
        return enqueued, src_hits
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                row = json.loads(text)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            stamp = row.get("enqueued_at")
            if isinstance(stamp, str) and (
                _DONE_MARKERS[0] in stamp or _DONE_MARKERS[1] in stamp
            ):
                enqueued += 1
            if row.get("src_run") in allowed:
                src_hits += 1
    return enqueued, src_hits


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    args = parser.parse_args(argv)
    body = census(args.root)
    json.dump(body, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    expected_counts = (
        48, 65, 67, 103, 56, 78, 40, 18, 51, 79, 56, 54, 58, 78, 43,
    )
    expected = {
        "direction_field": "dir_acc",
        "dir_acc_zero_rows_current_ok": 0,
        "hypothesis_v1": 879,
        "unparseable_proposal_json": 15,
        "proposal_json_excluding_prescreen": 894,
        "prescreen_files": 196,
        "prescreen_all_degraded_timeout": True,
        "done_enqueued_at_on_2026_11_17_or_18": 63,
        "done_src_run_in_window": 13,
        "runs": [
            {"id": run_id, "proposal_json_excluding_prescreen": count}
            for run_id, count in zip(RUN_IDS, expected_counts)
        ],
    }
    mismatched = [key for key in expected if body.get(key) != expected[key]]
    mismatched.extend(key for key in body if key not in expected)
    if mismatched:
        sys.stderr.write("ledger mismatch " + " ".join(mismatched) + "\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
