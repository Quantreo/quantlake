import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = Path(os.getenv("QUANTLAKE_DATA_ROOT", str(_PROJECT_ROOT / "data")))
BRONZE_ROOT = DATA_ROOT / "bronze"
SILVER_ROOT = DATA_ROOT / "silver"
GOLD_ROOT = DATA_ROOT / "gold"