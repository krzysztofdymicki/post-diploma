#!/usr/bin/env python3
"""
Main entry point for the sentiment analysis research workflow.

This script runs the complete research pipeline:
1. Load generated queries from query_agent.py
2. Execute searches using internet and research paper providers  
3. Store results in the database
4. Generate comprehensive reports

Usage:
    python main.py [options]
    
Examples:
    python main.py                          # Use latest queries, both providers
    python main.py --internet-only          # Only internet search  
    python main.py --papers-only            # Only research papers
    python main.py --max-queries 5          # Process only first 5 queries
"""

import sys
import os
import asyncio

# Add src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from run import main

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
