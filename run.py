#!/usr/bin/env python3
"""
run.py — Development entry point
Run with: python run.py
"""

import os
import sys

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import and run the app
from app.main import app

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)