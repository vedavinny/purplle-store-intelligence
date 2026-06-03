# analytics.py
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Optional
import numpy as np


class AnalyticsEngine:

    def __init__(self):
        self.events: deque = deque(maxlen=100_000)
        self.heatmaps: dict = {}
        self.zone_entries: dict = defaultdict(list)
        self.zone_dwells: dict = defaultdict(list)
        self.visitor_log: deque = deque(maxlen=50_000)

        # ✅ Track unique visitors separately
        self.unique_entry_visitors: set = set()
        self.unique_zone_visitors: set = set()
        self.engaged_visitors: set = set()

    def ingest(self, event: dict):

        self.events.append(event)

        etype = event.get("event_type")
        visitor_id = event.get("visitor_id")
        zone_id = event.get("zone_id")

        # ----------------------------------
        # ENTRY — store footfall
        # ----------------------------------
        if etype == "ENTRY":

            if visitor_id:
                self.unique_entry_visitors.add(visitor_id)

            self.visitor_log.append({
                "ts": event["timestamp"],
                "camera_id": event["camera_id"],
                "visitor_id": visitor_id
            })

        # ----------------------------------
        # ZONE_ENTER
        # ----------------------------------
        elif etype == "ZONE_ENTER":

            if visitor_id:
                self.unique_zone_visitors.add(visitor_id)

            self.visitor_log.append({
                "ts": event["timestamp"],
                "camera_id": event["camera_id"],
                "visitor_id": visitor_id
            })

            if zone_id:
                self.zone_entries[zone_id].append(
                    event["timestamp"]
                )

        # ----------------------------------
        # ZONE_EXIT — ✅ capture dwell here
        # ----------------------------------
        elif etype == "ZONE_EXIT":

            dwell_ms = event.get("dwell_ms", 0)
            dwell_s = dwell_ms / 1000

            # Only count meaningful dwells (>2s)
            if zone_id and dwell_s > 2:
                self.zone_dwells[zone_id].append(dwell_s)

        # ----------------------------------
        # ZONE_DWELL — long dwell event
        # ----------------------------------
        elif etype == "ZONE_DWELL":

            dwell_s = event.get("dwell_ms", 0) / 1000

            if zone_id and dwell_s > 0:
                self.zone_dwells[zone_id].append(dwell_s)

            if visitor_id:
                self.engaged_visitors.add(visitor_id)

            if zone_id:
                self.zone_entries[zone_id].append(
                    event["timestamp"]
                )

        # ----------------------------------
        # BILLING — mark as engaged
        # ----------------------------------
        elif etype == "BILLING":

            if visitor_id:
                self.engaged_visitors.add(visitor_id)

    # ───────────────────────────────────────────
    # Footfall
    # ───────────────────────────────────────────

    def get_footfall(
        self,
        camera_id: Optional[str],
        granularity: str,
        window_hours: int
    ) -> dict:

        cutoff = datetime.utcnow() - timedelta(hours=window_hours)
        bucket_map = defaultdict(set)

        for v in self.visitor_log:

            ts_str = v["ts"].replace("Z", "")

            try:
                ts = datetime.fromisoformat(ts_str)
            except Exception:
                continue

            if ts < cutoff:
                continue

            if camera_id and v["camera_id"] != camera_id:
                continue

            if granularity == "minute":
                key = ts.strftime("%Y-%m-%dT%H:%M")
            elif granularity == "hour":
                key = ts.strftime("%Y-%m-%dT%H:00")
            else:
                key = ts.strftime("%Y-%m-%d")

            # ✅ Count unique visitors per bucket
            vid = v.get("visitor_id", "unknown")
            bucket_map[key].add(vid)

        bucket_counts = {k: len(v) for k, v in bucket_map.items()}
        total = len(
            set(
                v.get("visitor_id")
                for v in self.visitor_log
                if v.get("visitor_id")
            )
        )

        peak = max(
            bucket_counts.items(),
            key=lambda x: x[1]
        ) if bucket_counts else ("—", 0)

        return {
            "camera_id": camera_id or "all",
            "granularity": granularity,
            "window_hours": window_hours,
            "total_visitors": total,
            "peak_bucket": peak[0],
            "peak_count": peak[1],
            "timeseries": [
                {"bucket": k, "count": v}
                for k, v in sorted(bucket_counts.items())
            ],
        }

    # ───────────────────────────────────────────
    # Heatmap
    # ───────────────────────────────────────────

    def get_heatmap(self, camera_id: str, window_minutes: int) -> dict:

        grid = self.heatmaps.get(camera_id)

        if grid is None:
            grid = np.zeros((36, 64))

        normalized = grid / (grid.max() + 1e-6)

        return {
            "camera_id": camera_id,
            "window_minutes": window_minutes,
            "grid": normalized.tolist(),
            "resolution": {
                "rows": normalized.shape[0],
                "cols": normalized.shape[1]
            },
            "hot_spots": self._top_hotspots(normalized, n=5),
        }

    def _top_hotspots(self, grid: np.ndarray, n: int = 5) -> list:

        flat = grid.flatten()
        top_indices = np.argpartition(flat, -n)[-n:]
        rows, cols = np.unravel_index(top_indices, grid.shape)

        return [
            {
                "row": int(r),
                "col": int(c),
                "intensity": float(grid[r, c]),
                "norm_x": float(c / grid.shape[1]),
                "norm_y": float(r / grid.shape[0]),
            }
            for r, c in sorted(
                zip(rows, cols),
                key=lambda x: -grid[x[0], x[1]]
            )
        ]

    # ───────────────────────────────────────────
    # Zone Stats
    # ───────────────────────────────────────────

    def get_zone_stats(
        self,
        camera_id: Optional[str],
        window_minutes: int
    ) -> dict:

        cutoff = datetime.utcnow() - timedelta(minutes=window_minutes)
        result = []

        all_zones = set(
            list(self.zone_entries.keys()) +
            list(self.zone_dwells.keys())
        )

        for zone_id in all_zones:

            dwells = self.zone_dwells.get(zone_id, [])
            entries = self.zone_entries.get(zone_id, [])

            # ✅ Count unique visitors per zone
            unique_zone_visitors = set()

            for e in self.events:
                if (
                    e.get("zone_id") == zone_id
                    and e.get("event_type") == "ZONE_ENTER"
                    and e.get("visitor_id")
                ):
                    ts_str = e["timestamp"].replace("Z", "")
                    try:
                        ts = datetime.fromisoformat(ts_str)
                        if ts >= cutoff:
                            unique_zone_visitors.add(
                                e["visitor_id"]
                            )
                    except Exception:
                        pass

            avg_dwell = np.mean(dwells) if dwells else 0
            max_dwell = max(dwells) if dwells else 0

            result.append({
                "zone_id": zone_id,
                # ✅ removed forced min=1
                "visitor_count": len(unique_zone_visitors),
                "avg_dwell_seconds": round(float(avg_dwell), 1),
                "max_dwell_seconds": round(float(max_dwell), 1)
            })

        return {
            "window_minutes": window_minutes,
            "zones": sorted(
                result,
                key=lambda x: -x["visitor_count"]
            )
        }

    # ───────────────────────────────────────────
    # Queue Analysis
    # ───────────────────────────────────────────

    def get_queue_stats(self, camera_id: str) -> dict:

        recent = [
            e for e in list(self.events)[-500:]
            if e.get("camera_id") == camera_id
            and e.get("event_type") == "crowd_count"
        ]

        if not recent:
            return {
                "camera_id": camera_id,
                "queue_depth": 0,
                "estimated_wait_minutes": 0
            }

        latest = recent[-1]
        zone_breakdown = latest.get("zone_breakdown", {})
        checkout_count = zone_breakdown.get("checkout", 0)
        service_rate = 0.5
        wait = checkout_count / service_rate if service_rate > 0 else 0

        return {
            "camera_id": camera_id,
            "queue_depth": checkout_count,
            "estimated_wait_minutes": round(wait, 1),
            "zone_breakdown": zone_breakdown,
            "sampled_at": latest.get("timestamp"),
        }

    # ───────────────────────────────────────────
    # Store Summary
    # ───────────────────────────────────────────

    def get_store_summary(self) -> dict:

        today = datetime.utcnow().date().isoformat()

        # ✅ Count ALL unique visitors, not just today
        all_visitors = len(
            set(
                v["visitor_id"]
                for v in self.visitor_log
                if v.get("visitor_id")
            )
        )

        # Today's visitors separately
        today_visitors = len(
            set(
                v["visitor_id"]
                for v in self.visitor_log
                if v["ts"][:10] == today
                and v.get("visitor_id")
            )
        )

        all_dwells = [
            d
            for dwells in self.zone_dwells.values()
            for d in dwells
        ]

        avg_dwell = round(
            float(np.mean(all_dwells)), 1
        ) if all_dwells else 0

        hourly = defaultdict(set)
        for v in self.visitor_log:
            if v.get("visitor_id"):
                hour = v["ts"][11:13]
                hourly[hour].add(v["visitor_id"])

        peak_hour = max(
            hourly.items(),
            key=lambda x: len(x[1])
        )[0] if hourly else "N/A"

        return {
            "date": today,
            "total_visitors_today": all_visitors,  # ✅ all unique
            "today_only": today_visitors,
            "avg_dwell_seconds": avg_dwell,
            "peak_hour": f"{peak_hour}:00",
            "active_cameras": len(self.heatmaps),
            "zones_tracked": len(
                set(
                    list(self.zone_entries.keys()) +
                    list(self.zone_dwells.keys())
                )
            ),
            "unique_entry_visitors": len(self.unique_entry_visitors),
            "unique_zone_visitors": len(self.unique_zone_visitors),
            "engaged_visitors": len(self.engaged_visitors),
        }