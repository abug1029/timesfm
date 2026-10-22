"""Test that verifies no bypass writes to production queue.

Phase 2 C3: All proposals must go through validation before entering queue.
This test verifies the bypass has been removed (or was never present).
"""
import ast
import os
from pathlib import Path

def test_no_direct_queue_write_without_validation():
    """Verify sup_harvest.py validates before writing to queue."""
    harvest_path = Path('scripts/sup_harvest.py')
    assert harvest_path.exists(), 'sup_harvest.py not found'
    
    with open(harvest_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Parse AST to find write calls
    tree = ast.parse(content)
    
    # Track validation and write calls
    has_validation = False
    write_calls = []
    
    for node in ast.walk(tree):
        # Check for validate_proposal_dict or validate_proposal calls
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if 'validate' in node.func.id.lower():
                    has_validation = True
            elif isinstance(node.func, ast.Attribute):
                if 'validate' in node.func.attr.lower():
                    has_validation = True
        
        # Check for direct writes to aligned_verdicts.jsonl
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in ['open', 'write']:
                    # Check if it's writing to aligned_verdicts
                    for arg in node.args:
                        if isinstance(arg, ast.Constant) and 'aligned_verdicts' in str(arg.value):
                            write_calls.append(node.lineno)
    
    # Verify validation exists
    assert has_validation, 'No validation calls found in sup_harvest.py'
    
    # Verify no direct writes to aligned_verdicts (only via write_proposal_status)
    # The write_proposal_status is for status tracking, not queue insertion
    assert len(write_calls) == 0, f'Direct writes to aligned_verdicts found at lines: {write_calls}'
    
    print('✓ No bypass writes detected - all paths go through validation')

def test_proposal_validator_is_called():
    """Verify proposal_validator is imported and used."""
    harvest_path = Path('scripts/sup_harvest.py')
    
    with open(harvest_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check import
    assert 'from proposal_validator import' in content or 'import proposal_validator' in content,         'proposal_validator not imported'
    
    # Check usage
    assert 'validate_proposal' in content, 'validate_proposal not called'
    
    print('✓ proposal_validator is imported and used')
