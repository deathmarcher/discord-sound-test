import sys
import pathlib

# Ensure project root is on sys.path so tests can import the package
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
