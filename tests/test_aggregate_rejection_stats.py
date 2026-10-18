import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))


def test_render_rejection_detail_section():
    """render_rejection_detail_section 从 rejected_proposals.jsonl 生成 Markdown 节"""
    from aggregate_rejection_stats import render_rejection_detail_section

    with tempfile.TemporaryDirectory() as tmpdir:
        rf = os.path.join(tmpdir, 'rejected.jsonl')
        with open(rf, 'w') as f:
            f.write(json.dumps({'proposal_id': 'p1', 'version': 1, 'reject_reason': 'schema_mismatch', 'quality_score': None, 'symbol': 'm', 'cov_override': 'ma20', 'covariate_family': 'momentum', 'run_id': 'run1'}) + '\n')
            f.write(json.dumps({'proposal_id': 'p2', 'version': 2, 'reject_reason': 'quality_below_threshold', 'quality_score': -3.5, 'symbol': 'rb', 'cov_override': 'rsi', 'covariate_family': 'momentum', 'run_id': 'run1'}) + '\n')

        section = render_rejection_detail_section(rf)
        assert 'p1' in section
        assert 'schema_mismatch' in section
        assert 'p2' in section
        assert 'quality_below_threshold' in section


def test_output_file_defined():
    """OUTPUT_FILE 已定义"""
    import aggregate_rejection_stats as ars

    assert hasattr(ars, 'OUTPUT_FILE')
    assert ars.OUTPUT_FILE.endswith('known_rejections.inc.md')


def test_aggregate_rejections_function_exists():
    """aggregate_rejections 函数存在"""
    import aggregate_rejection_stats as ars

    assert hasattr(ars, 'aggregate_rejections')
    assert callable(ars.aggregate_rejections)
