import os
from pathlib import Path

BASE_DIR = Path(os.getenv("BRICKWORKS_BASE_DIR", Path.cwd()))
CORE_DIR = Path(__file__).resolve().parent
