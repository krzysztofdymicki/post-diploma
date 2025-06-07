#!/usr/bin/env python3
"""
Test script for weighted average calculation with null credibility handling.
Tests the new logic where credibility_score can be None for research papers.
"""

import sys
sys.path.append('src')

from quality_assessment_module import QualityAssessmentModule, ASSESSMENT_WEIGHTS
from database import Database

def manual_calculate_weighted_average_with_null(relevance_score, credibility_score, 
                                               solidity_score, overall_usefulness_score):
    """Manual calculation for comparison."""
    if credibility_score is not None:
        # Standard calculation with all scores
        weighted_sum = (
            relevance_score * ASSESSMENT_WEIGHTS['relevance'] +
            credibility_score * ASSESSMENT_WEIGHTS['credibility'] +
            solidity_score * ASSESSMENT_WEIGHTS['solidity'] +
            overall_usefulness_score * ASSESSMENT_WEIGHTS['overall_usefulness']
        )
    else:
        # Redistribute credibility weight proportionally among other scores
        total_remaining_weight = (ASSESSMENT_WEIGHTS['relevance'] + 
                                ASSESSMENT_WEIGHTS['solidity'] + 
                                ASSESSMENT_WEIGHTS['overall_usefulness'])
        
        # Calculate redistribution factor
        redistribution_factor = 1.0 / total_remaining_weight
        
        adjusted_weights = {
            'relevance': ASSESSMENT_WEIGHTS['relevance'] * redistribution_factor,
            'solidity': ASSESSMENT_WEIGHTS['solidity'] * redistribution_factor,
            'overall_usefulness': ASSESSMENT_WEIGHTS['overall_usefulness'] * redistribution_factor
        }
        
        weighted_sum = (
            relevance_score * adjusted_weights['relevance'] +
            solidity_score * adjusted_weights['solidity'] +
            overall_usefulness_score * adjusted_weights['overall_usefulness']
        )
    
    return round(weighted_sum, 2)

def test_weighted_average_with_null():
    """Test the weighted average calculation with null credibility."""
    print("=== Testing Weighted Average Calculation with Null Credibility ===")
    print(f"Weights: {ASSESSMENT_WEIGHTS}")
    print(f"Sum of weights: {sum(ASSESSMENT_WEIGHTS.values())}")
    
    # Create assessment module instance for testing
    db = Database(':memory:')  # In-memory database for testing
    assessment_module = QualityAssessmentModule(db, api_key='test-key')
    
    test_cases = [
        # Normal cases with credibility
        {
            'name': 'Perfect scores (with credibility)',
            'scores': (5, 5, 5, 5),
            'expected_manual': manual_calculate_weighted_average_with_null(5, 5, 5, 5)
        },
        {
            'name': 'Mixed scores (with credibility)',
            'scores': (4, 3, 4, 4),
            'expected_manual': manual_calculate_weighted_average_with_null(4, 3, 4, 4)
        },
        # Research paper cases with null credibility
        {
            'name': 'Perfect scores (research paper - null credibility)',
            'scores': (5, None, 5, 5),
            'expected_manual': manual_calculate_weighted_average_with_null(5, None, 5, 5)
        },
        {
            'name': 'High relevance, low others (research paper)',
            'scores': (5, None, 2, 2),
            'expected_manual': manual_calculate_weighted_average_with_null(5, None, 2, 2)
        },
        {
            'name': 'Mixed scores (research paper)',
            'scores': (4, None, 3, 4),
            'expected_manual': manual_calculate_weighted_average_with_null(4, None, 3, 4)
        },
        {
            'name': 'All minimum scores (research paper)',
            'scores': (1, None, 1, 1),
            'expected_manual': manual_calculate_weighted_average_with_null(1, None, 1, 1)
        },
    ]
    
    all_passed = True
    
    for test_case in test_cases:
        relevance, credibility, solidity, usefulness = test_case['scores']
        expected = test_case['expected_manual']
        
        try:
            actual = assessment_module.calculate_weighted_average(relevance, credibility, solidity, usefulness)
            manual = test_case['expected_manual']
            
            match = abs(actual - expected) < 0.0001  # Allow for small floating point differences
            
            print(f"\nTest: {test_case['name']}")
            print(f"  Scores: Relevance={relevance}, Credibility={credibility}, Solidity={solidity}, Usefulness={usefulness}")
            print(f"  Manual calculation: {manual}")
            print(f"  Expected: {expected}")
            print(f"  Actual: {actual}")
            print(f"  Match: {'✓' if match else '✗'}")
            
            if not match:
                all_passed = False
                print(f"  ERROR: Expected {expected}, got {actual}")
                
        except Exception as e:
            print(f"\nTest: {test_case['name']}")
            print(f"  ERROR: {e}")
            all_passed = False
    
    print(f"\n=== Test Results ===")
    print(f"All tests passed: {'✓' if all_passed else '✗'}")
    
    # Additional verification: Check that weights for null credibility sum to 1.0
    total_remaining_weight = (ASSESSMENT_WEIGHTS['relevance'] + 
                            ASSESSMENT_WEIGHTS['solidity'] + 
                            ASSESSMENT_WEIGHTS['overall_usefulness'])
    
    redistribution_factor = 1.0 / total_remaining_weight
    
    adjusted_weights = {
        'relevance': ASSESSMENT_WEIGHTS['relevance'] * redistribution_factor,
        'solidity': ASSESSMENT_WEIGHTS['solidity'] * redistribution_factor,
        'overall_usefulness': ASSESSMENT_WEIGHTS['overall_usefulness'] * redistribution_factor
    }
    
    adjusted_sum = sum(adjusted_weights.values())
    
    print(f"\n=== Weight Redistribution Verification ===")
    print(f"Original weights (without credibility): {total_remaining_weight}")
    print(f"Redistribution factor: {redistribution_factor}")
    print(f"Adjusted weights: {adjusted_weights}")
    print(f"Adjusted weights sum: {adjusted_sum}")
    print(f"Sum equals 1.0: {'✓' if abs(adjusted_sum - 1.0) < 0.0001 else '✗'}")
    
    return all_passed

if __name__ == '__main__':
    success = test_weighted_average_with_null()
    sys.exit(0 if success else 1)
