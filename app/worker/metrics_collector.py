"""
Metrics Collector — reads raw latency rows from agent_metrics,
computes P50 / P95 / P99 per channel, and writes summary rows back.

Run as a standalone background task (e.g. every 60 s) or import
collect_and_store_percentiles() and schedule it via asyncio.

Usage (standalone):
    python -m app.worker.metrics_collector
"""

import asyncio
import logging
import os
import statistics
from datetime import datetime, timezone

from app.db.session import get_db_pool, init_db_pool

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

COLLECTION_INTERVAL_SECONDS = int(os.getenv("METRICS_INTERVAL_SECONDS", "60"))

# How far back to look when computing percentiles
LOOKBACK_INTERVAL = "1 hour"


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------

def _percentile(data: list[float], pct: float) -> float:
    """Return the p-th percentile of a sorted list (0–100 scale)."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    idx = (pct / 100) * (len(sorted_data) - 1)
    lower = int(idx)
    upper = min(lower + 1, len(sorted_data) - 1)
    frac = idx - lower
    return sorted_data[lower] + frac * (sorted_data[upper] - sorted_data[lower])


async def collect_and_store_percentiles() -> None:
    """
    1. Fetch raw response_latency_ms rows from the last LOOKBACK_INTERVAL.
    2. Group by channel.
    3. Compute P50, P95, P99 and mean.
    4. Write summary metrics back to agent_metrics.
    5. Log a structured summary line.
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        # ── Read raw latency samples ────────────────────────────────────────
        rows = await conn.fetch(
            f"""
            SELECT channel, metric_value
            FROM agent_metrics
            WHERE metric_name = 'response_latency_ms'
              AND recorded_at > NOW() - INTERVAL '{LOOKBACK_INTERVAL}'
            ORDER BY recorded_at DESC
            """
        )

    if not rows:
        logger.info("No latency samples in the last %s — skipping.", LOOKBACK_INTERVAL)
        return

    # Group samples by channel
    by_channel: dict[str, list[float]] = {}
    for row in rows:
        ch = row["channel"] or "unknown"
        by_channel.setdefault(ch, []).append(float(row["metric_value"]))

    # ── Compute + persist percentiles ────────────────────────────────────
    now = datetime.now(timezone.utc)
    insert_rows: list[tuple] = []

    for channel, samples in by_channel.items():
        p50  = _percentile(samples, 50)
        p95  = _percentile(samples, 95)
        p99  = _percentile(samples, 99)
        mean = statistics.mean(samples)
        n    = len(samples)

        dimensions = {"lookback": LOOKBACK_INTERVAL, "sample_count": n}

        for metric_name, value in [
            ("latency_p50_ms",  p50),
            ("latency_p95_ms",  p95),
            ("latency_p99_ms",  p99),
            ("latency_mean_ms", mean),
        ]:
            insert_rows.append((metric_name, value, channel, dimensions, now))

        logger.info(
            "Metrics [%s] samples=%d  P50=%.0fms  P95=%.0fms  P99=%.0fms  mean=%.0fms",
            channel, n, p50, p95, p99, mean,
        )

    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO agent_metrics
                (metric_name, metric_value, channel, dimensions, recorded_at)
            VALUES ($1, $2, $3, $4::jsonb, $5)
            """,
            [
                (name, value, ch, __import__("json").dumps(dims), ts)
                for name, value, ch, dims, ts in insert_rows
            ],
        )

    logger.info("Stored %d percentile rows for %d channels.", len(insert_rows), len(by_channel))


# ---------------------------------------------------------------------------
# Escalation-rate collector
# ---------------------------------------------------------------------------

async def collect_escalation_rate() -> None:
    """
    Compute escalation rate per channel over the last hour and store it.
    Escalation rate = escalated tickets / total tickets.
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT
                source_channel                                         AS channel,
                COUNT(*)                                               AS total,
                COUNT(*) FILTER (WHERE status = 'escalated')          AS escalated
            FROM tickets
            WHERE created_at > NOW() - INTERVAL '{LOOKBACK_INTERVAL}'
            GROUP BY source_channel
            """
        )

    if not rows:
        return

    now = datetime.now(timezone.utc)
    insert_rows = []
    for row in rows:
        channel  = row["channel"]
        total    = row["total"] or 1          # avoid /0
        rate_pct = (row["escalated"] / total) * 100
        insert_rows.append(
            ("escalation_rate_pct", rate_pct, channel, {}, now)
        )
        logger.info("Escalation rate [%s]: %.1f%%  (%d/%d)", channel, rate_pct, row["escalated"], total)

    async with pool.acquire() as conn:
        import json
        await conn.executemany(
            """
            INSERT INTO agent_metrics
                (metric_name, metric_value, channel, dimensions, recorded_at)
            VALUES ($1, $2, $3, $4::jsonb, $5)
            """,
            [(name, val, ch, json.dumps(dims), ts) for name, val, ch, dims, ts in insert_rows],
        )


# ---------------------------------------------------------------------------
# Background loop
# ---------------------------------------------------------------------------

async def run_collector_loop() -> None:
    """Collect metrics on a fixed interval until cancelled."""
    await init_db_pool()
    logger.info("Metrics collector started (interval=%ds).", COLLECTION_INTERVAL_SECONDS)
    while True:
        try:
            await collect_and_store_percentiles()
            await collect_escalation_rate()
        except Exception as exc:
            logger.error("Metrics collection error: %s", exc)
        await asyncio.sleep(COLLECTION_INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(run_collector_loop())
