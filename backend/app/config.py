"""Dates and the day-ahead gate used across ingest and scoring."""

from datetime import date, time
from zoneinfo import ZoneInfo

LONDON = ZoneInfo("Europe/London")

# Business assumption for this desk, not a timestamp from the Elexon API.
# Treated as the N2EX day-ahead order-book closure. A forecast published
# after this clock time is left out of the decision view.
GATE_LOCAL = time(9, 50)

# Assignment scope is January 2026 only. Clock-change days are not fetched
# or served. The interval builder still uses the Europe/London civil day so
# a date outside this window is not forced into 48 periods.
DELIVERY_FROM = date(2026, 1, 1)
DELIVERY_TO = date(2026, 1, 31)

# Publish window is wider than the delivery month so 1 January is covered
# by forecasts issued on 31 December, and post-gate runs stay in the file
# for the lookahead checks to reject.
PUBLISH_FROM = date(2025, 12, 30)
PUBLISH_TO = date(2026, 2, 1)

ELEXON_BASE = "https://data.elexon.co.uk/bmrs/api/v1/datasets"
FUELHH_URL = (
    "https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/FUELHH/stream"
)
WINDFOR_URL = (
    "https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/WINDFOR/stream"
)
