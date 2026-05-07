"""End of v0.6.3 - USDA NASS raw output, no connector.

Shows how NASS returns: a `data` array of objects with string-formatted
values ("7,400,000"), suppression codes ("(D)", "(Z)"), and string year.

"""
import json
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

URL = "https://quickstats.nass.usda.gov/api/api_GET/"

resp = httpx.get(URL, params={
    "key":             os.environ["NASS_API_KEY"],
    "commodity_desc":  "WHEAT",
    "class_desc":      "WINTER",
    "statisticcat_desc": "AREA PLANTED",
    "agg_level_desc":  "STATE",
    "source_desc":     "SURVEY",
    "year__GE":        2022,
    "year__LE":        2024,
    "format":          "JSON",
    "unit_desc":       "ACRES",
    "state_alpha":     ["KS", "OK"],
}, timeout=30)
resp.raise_for_status()

data = resp.json().get("data", [])
print(f"{len(data)} rows returned\n")
print(json.dumps(data[:2], indent=2))
