import re
from cascade.laya_prescreen import _build_state, _extract_relevant_history

CJK_RE = re.compile(r'[一-鿿]')

class TestStateEnglishOnly:
    def test_build_state_sector_is_english(self):
        """state['sector'] must be English, not '黑色系' etc."""
        state = _build_state(
            proposal={'variant_id': 'v1'},
            symbol='rb',  # black_metals
            verdict_history=None,
            covariate_menu=None,
        )
        assert state['sector'] in ('ferrous', 'black_metals'), f"got {state['sector']!r}"
        assert not CJK_RE.search(state['sector']), f"sector contains Chinese: {state['sector']!r}"

    def test_build_state_default_sector_unknown(self):
        """Unknown symbol's sector defaults to 'unknown', not '未知'."""
        state = _build_state(
            proposal={'variant_id': 'v1'},
            symbol='unknown_symbol_xyz',
            verdict_history=None,
            covariate_menu=None,
        )
        assert state['sector'] == 'unknown', f"got {state['sector']!r}"

    def test_extract_relevant_history_no_chinese(self):
        """History summary must not contain Chinese templates."""
        history = [
            {'symbol': 'rb', 'gate_pass': True, 'cov_override': 'x', 'cov_family': 'f1', 'dir_acc': 0.5, 'decided_at': '2026-01-01'},
            {'symbol': 'i', 'gate_pass': True, 'cov_override': 'y', 'cov_family': 'f2', 'dir_acc': 0.3, 'decided_at': '2026-01-02'},
        ]
        result = _extract_relevant_history(history, 'rb')
        assert not CJK_RE.search(result), f"history contains Chinese:\n{result}"

    def test_extract_relevant_history_empty(self):
        """Empty history returns English default message."""
        result = _extract_relevant_history(None, 'rb')
        assert not CJK_RE.search(result), f"empty history has Chinese: {result!r}"
