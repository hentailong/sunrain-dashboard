"""Minute positions for Dengta; retain the original observation and source clocks."""
import json
from datetime import datetime, timedelta, timezone

TZ = timezone(timedelta(hours=8))


def nearest_minute(value: str, statistical_date: str | None = None) -> str:
    at = datetime.fromisoformat(value).astimezone(TZ)
    rounded = (at + timedelta(seconds=30)).replace(second=0, microsecond=0)
    # A daily cumulative total must not leak into the following day's reset.
    day = datetime.fromisoformat(statistical_date).replace(tzinfo=TZ) if statistical_date else at.replace(hour=0, minute=0, second=0, microsecond=0)
    rounded = max(day, min(rounded, day + timedelta(days=1, minutes=-1)))
    return rounded.isoformat()


def normalize_history(conn) -> int:
    """Idempotent metadata migration; raw values and original times stay intact."""
    changed = 0
    for row in conn.execute("SELECT id,collected_at,metadata_json FROM observations WHERE source='dengta'").fetchall():
        meta = json.loads(row['metadata_json'] or '{}')
        if meta.get('sample_minute'):
            continue
        meta['sample_minute'] = nearest_minute(row['collected_at'], meta.get('statistical_date'))
        conn.execute('UPDATE observations SET metadata_json=? WHERE id=?',
                     (json.dumps(meta, ensure_ascii=False), row['id']))
        changed += 1
    return changed


def minute_rows(rows):
    """Return the last actual observation per metric/minute, without filling gaps."""
    latest = {}
    for row in rows:
        meta = json.loads(row['metadata_json'] or '{}')
        minute = meta.get('sample_minute') or nearest_minute(row['collected_at'], meta.get('statistical_date'))
        key = (row['metric'], minute)
        previous = latest.get(key)
        if previous is None or (row['collected_at'], row['id']) > (previous['collected_at'], previous['id']):
            latest[key] = dict(row, chart_time=minute)
    return sorted(latest.values(), key=lambda row: (row['chart_time'], row['metric']))
