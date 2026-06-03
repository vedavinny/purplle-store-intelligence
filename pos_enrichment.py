import pandas as pd
import json
from datetime import datetime, timedelta

# -------------------------
# Load POS transactions
# -------------------------
pos_df = pd.read_csv("POS_-_sample_transactions.csv")

# Group by order_time — same timestamp = one transaction
pos_grouped = pos_df.groupby("order_time").agg(
    total_amount=("total_amount", "sum"),
    item_count=("product_id", "count"),
    brands=("brand_name", lambda x: list(x.unique())),
    products=("product_id", list),
    store_id=("store_id", "first")
).reset_index()

pos_grouped["order_time_parsed"] = pd.to_datetime(
    pos_grouped["order_time"],
    format="%H:%M:%S"
)

print(f"Total transactions: {len(pos_grouped)}")
print(pos_grouped[["order_time", "total_amount", "item_count"]].head(10))

# -------------------------
# Load BILLING events
# -------------------------
billing_events = []

with open("output/events.jsonl", "r") as f:
    for i, line in enumerate(f):
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
            if event["event_type"] == "BILLING":
                billing_events.append(event)
        except json.JSONDecodeError as e:
            print(f"Skipping malformed line {i+1}: {e}")

# -------------------------
# Match BILLING event to
# nearest POS transaction
# by time window (±5 min)
# -------------------------
MATCH_WINDOW_MINUTES = 5
enriched = []
used_transactions = set()

# Replace the matching section entirely with this:
for event in billing_events:

    event_time = datetime.fromisoformat(
        event["timestamp"].replace("Z", "+00:00")
    )
    event_hms = timedelta(
        hours=event_time.hour,
        minutes=event_time.minute,
        seconds=event_time.second
    )

    best_match = None
    best_diff = timedelta(hours=24)  # no window — just find closest

    for idx, row in pos_grouped.iterrows():

        if idx in used_transactions:
            continue

        pos_hms = timedelta(
            hours=row["order_time_parsed"].hour,
            minutes=row["order_time_parsed"].minute,
            seconds=row["order_time_parsed"].second
        )

        diff = abs(event_hms - pos_hms)

        if diff < best_diff:
            best_diff = diff
            best_match = (idx, row)

    if best_match:
        idx, row = best_match
        used_transactions.add(idx)

        enriched_event = {
            **event,
            "pos_matched": True,
            "pos_order_time": row["order_time"],
            "pos_total_amount": round(row["total_amount"], 2),
            "pos_item_count": int(row["item_count"]),
            "pos_brands": row["brands"],
            "pos_time_diff_seconds": int(best_diff.total_seconds())
        }
    else:
        enriched_event = {
            **event,
            "pos_matched": False,
            "pos_order_time": None,
            "pos_total_amount": None,
            "pos_item_count": None,
            "pos_brands": [],
            "pos_time_diff_seconds": None
        }

    enriched.append(enriched_event)
    print(
        f"BILLING {event['visitor_id']} @ {event['timestamp'][11:19]} "
        f"→ POS match: {enriched_event.get('pos_order_time')} "
        f"₹{enriched_event.get('pos_total_amount')}"
    )
# -------------------------
# Save enriched events
# -------------------------
with open("output/billing_enriched.jsonl", "w") as f:
    for e in enriched:
        f.write(json.dumps(e) + "\n")

print(f"\nSaved {len(enriched)} enriched billing events")
print(f"Matched: {sum(1 for e in enriched if e['pos_matched'])}")
print(f"Unmatched: {sum(1 for e in enriched if not e['pos_matched'])}")