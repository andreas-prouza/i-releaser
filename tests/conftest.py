import os, sys

# The repository root, so `etc` and `modules` are found
ROOT_DIR = os.path.realpath(f"{os.path.dirname(__file__)}/..")
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, os.path.dirname(__file__))
