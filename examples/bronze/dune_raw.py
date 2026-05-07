"""End of v0.6.4 - Dune raw query result, no connector wrapper.

Shows what dune_client.get_latest_result returns: a list of dicts
where keys are the SQL column names, timestamp is a string with
" UTC" suffix.

"""
import os

from dune_client.client import DuneClient
from dotenv import load_dotenv

load_dotenv()
QUERY_ID = 7445139   # Replace with your own saved query_id

client = DuneClient(api_key=os.environ["DUNE_API_KEY"])
result = client.get_latest_result(QUERY_ID)
rows = result.result.rows

print(f"{len(rows)} rows, first 3:")
for r in rows[:3]:
    print(r)
