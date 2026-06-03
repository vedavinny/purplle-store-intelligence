# event_loader.py
import json

def load_events(engine):

    loaded = 0
    skipped = 0

    try:
        with open("output/events.jsonl", "r") as f:

            for i, line in enumerate(f):

                line = line.strip()

                if not line:
                    continue

                try:
                    event = json.loads(line)
                    engine.ingest(event)
                    loaded += 1

                except json.JSONDecodeError as e:
                    skipped += 1
                    print(f"Skipping malformed line {i+1}: {e}")

    except FileNotFoundError:
        print("events.jsonl not found — starting fresh")

    print(f"Loaded {loaded} events, skipped {skipped} malformed lines")