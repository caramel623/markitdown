"""Convenience launcher: python run_gui.py"""
import os
import sys

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)

from markitdown_gui import main

if __name__ == "__main__":
    sys.exit(main())
