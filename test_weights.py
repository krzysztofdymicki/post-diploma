#!/usr/bin/env python3
"""
Test script for weighted average calculation in quality assessment.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

from quality_assessment_module import QualityAssessmentModule, ASSESSMENT_WEIGHTS
from database import Database
import tempfile

def test_weighted_average():
    """Test the weighted average calculation function."""
    
    # Create a temporary database
    with tempfile.NamedTemporaryFile(delete=False) as temp_db:
        db = Database(temp_db.name)
        
        # Initialize the assessment module
        # Note: This will fail without GEMINI_API_KEY, but we can still test the weights calculation
        try:
            module = QualityAssessmentModule(db)
        except ValueError as e:
            print(f"Note: Can't initialize full module without API key: {e}")
            print("But we can still test the weights calculation...")
        
        # Test different score combinations
        test_cases = [
            {
                'name': 'Perfect scores',
                'scores': (5, 5, 5, 5),
                'expected': 5.0
            },
            {
                'name': 'All minimum scores',
                'scores': (1, 1, 1, 1),
                'expected': 1.0
            },
            {
                'name': 'High relevance, low others',
                'scores': (5, 1, 1, 1),
                'expected': 5 * 0.35 + 1 * 0.25 + 1 * 0.20 + 1 * 0.20  # = 1.75 + 0.25 + 0.20 + 0.20 = 2.40
            },
            {
                'name': 'High credibility, low others', 
                'scores': (1, 5, 1, 1),
                'expected': 1 * 0.35 + 5 * 0.25 + 1 * 0.20 + 1 * 0.20  # = 0.35 + 1.25 + 0.20 + 0.20 = 2.00
            },
            {
                'name': 'Mixed scores (realistic case)',
                'scores': (4, 3, 4, 4),
                'expected': 4 * 0.35 + 3 * 0.25 + 4 * 0.20 + 4 * 0.20  # = 1.40 + 0.75 + 0.80 + 0.80 = 3.75
            }
        ]
        
        print("=== Testing Weighted Average Calculation ===")
        print(f"Weights: {ASSESSMENT_WEIGHTS}")
        print(f"Sum of weights: {sum(ASSESSMENT_WEIGHTS.values())}")
        print()
        
        for case in test_cases:
            relevance, credibility, solidity, usefulness = case['scores']
            
            # Manual calculation
            manual_result = (
                relevance * ASSESSMENT_WEIGHTS['relevance'] +
                credibility * ASSESSMENT_WEIGHTS['credibility'] +
                solidity * ASSESSMENT_WEIGHTS['solidity'] +
                usefulness * ASSESSMENT_WEIGHTS['overall_usefulness']
            )
            manual_result = round(manual_result, 2)
            
            print(f"Test: {case['name']}")
            print(f"  Scores: Relevance={relevance}, Credibility={credibility}, Solidity={solidity}, Usefulness={usefulness}")
            print(f"  Manual calculation: {manual_result}")
            print(f"  Expected: {case['expected']}")
            print(f"  Match: {'✓' if abs(manual_result - case['expected']) < 0.01 else '✗'}")
            print()

if __name__ == "__main__":
    test_weighted_average()
