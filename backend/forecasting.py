"""Forecast comparable series using time buckets and chronological backtests."""
from datetime import datetime, timedelta
import math


def predict(values, steps, model):
    if model == 'naive':
        return [values[-1]] * steps
    recent = values[-min(24, len(values)):]
    # Damp the recent slope so a short spike cannot grow indefinitely.
    slope = (recent[-1] - recent[0]) / max(1, len(recent) - 1)
    return [max(0, values[-1] + slope * sum(0.9 ** j for j in range(1, i + 1)))
            for i in range(1, steps + 1)]


def forecast_rows(rows, hours, current):
    hourly = hours <= 24
    interval = timedelta(hours=1) if hourly else timedelta(days=1)
    required, steps = (168, 24) if hourly else (28, 7)
    end = current.replace(minute=0, second=0, microsecond=0)
    if not hourly:
        end = end.replace(hour=0)
    start = end - interval * (required - 1)
    buckets = {}
    daily = False
    for row in rows:
        if row.get('value') is None or isinstance(row['value'], bool):
            continue
        value = float(row['value'])
        if not math.isfinite(value):
            continue
        stamp = row.get('source_time') or row['collected_at']
        try:
            date = datetime.fromisoformat(stamp)
        except (TypeError, ValueError):
            continue
        if date.tzinfo is None:
            date = date.replace(tzinfo=current.tzinfo)
        date = date.astimezone(current.tzinfo)
        if date > current:
            continue
        daily |= bool(row.get('source_time') and len(row['source_time']) == 10)
        bucket = date.replace(minute=0, second=0, microsecond=0)
        if not hourly:
            bucket = bucket.replace(hour=0)
        if start <= bucket <= end:
            # Rows are chronological; the final observation in each bucket wins.
            buckets[bucket] = value
    if hourly and daily:
        return {'available': False, 'reason': '该指标仅发布日榜数据，无法满足24小时预测需要的7天小时数据。'}
    coverage = len(buckets) / required
    if len(buckets) < 2 or min(buckets) > start or coverage < .8:
        return {'available': False, 'coverage': coverage,
                'reason': f'需要至少{"7天小时" if hourly else "28天日"}数据且覆盖率≥80%；当前窗口有{len(buckets)}/{required}个有效时段（{coverage:.0%}）。缺失值不计为零。'}
    if max(buckets) < end - interval * 2:
        return {'available': False, 'reason': '来源数据已过期，暂停预测，待自动采集恢复。'}
    # Backtests only score observed targets; gaps remain absent in storage.
    # Carry forward past readings for the model, never interpolate from the future.
    sequence = []
    observed = []
    last = None
    for index in range(required):
        stamp = start + interval * index
        observed.append(stamp in buckets)
        if stamp in buckets:
            last = buckets[stamp]
        sequence.append(last)
    errors = {}
    residuals = {}
    for model in ('naive', 'damped'):
        scored = []
        for origin in range(required // 2, required - steps + 1, max(1, steps // 2)):
            predicted = predict(sequence[:origin], steps, model)
            scored.extend(abs(guess - sequence[origin + i]) for i, guess in enumerate(predicted)
                          if observed[origin + i])
        if scored:
            errors[model] = sum(scored) / len(scored)
            residuals[model] = scored
    if not errors:
        return {'available': False, 'reason': '缺少可用于滚动回测的真实目标时段，暂停预测。'}
    model = min(errors, key=errors.get)
    actual_end = max(buckets)
    sequence = sequence[:int((actual_end - start) / interval) + 1]
    guesses = predict(sequence, steps, model)
    absolute = sorted(residuals[model])
    radius = absolute[min(len(absolute) - 1, math.ceil(len(absolute) * .95) - 1)]
    points = [{'time': (actual_end + interval * (i + 1)).isoformat(), 'value': guess,
               'lower': max(0, guess - radius), 'upper': guess + radius}
              for i, guess in enumerate(guesses)]
    return {'available': True, 'points': points, 'model': '朴素基线' if model == 'naive' else '阻尼趋势',
            'training_samples': len(buckets), 'training_until': actual_end.isoformat(),
            'error': errors[model], 'backtest_errors': errors, 'coverage': coverage,
            'interval_method': '滚动回测绝对误差95%分位估计区间', 'backtest_targets': len(absolute)}
