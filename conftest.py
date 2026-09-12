"""确保 pytest 能从项目根目录 import tools.* 和 achievement_graph.*。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
