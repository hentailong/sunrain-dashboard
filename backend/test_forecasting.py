from datetime import datetime, timedelta, timezone
import unittest

from backend.forecasting import forecast_rows


class ForecastTests(unittest.TestCase):
    def setUp(self):
        self.current = datetime(2026, 11, 9, 16, tzinfo=timezone(timedelta(hours=8)))

    def hourly(self, count, step=1):
        return [{'collected_at': (self.current - timedelta(hours=count - 1 - i)).isoformat(),
                 'value': 100 + i * step} for i in range(count)]

    def test_15_minute_samples_cannot_substitute_for_seven_days(self):
        rows = [{'collected_at': (self.current - timedelta(minutes=i * 15)).isoformat(),
                 'value': 100} for i in reversed(range(168))]
        self.assertFalse(forecast_rows(rows, 24, self.current)['available'])

    def test_daily_data_cannot_produce_hourly_forecast(self):
        rows = [{'collected_at': self.current.isoformat(), 'source_time': '2026-11-08', 'value': 9164}]
        self.assertFalse(forecast_rows(rows, 24, self.current)['available'])

    def test_constant_series_selects_naive_baseline(self):
        result = forecast_rows(self.hourly(168, step=0), 24, self.current)
        self.assertTrue(result['available'])
        self.assertEqual(result['model'], '朴素基线')
        self.assertEqual(result['error'], 0)
        self.assertEqual(len(result['points']), 24)

    def test_future_observations_cannot_leak_into_training_or_backtest(self):
        rows = self.hourly(168)
        first = forecast_rows(rows, 24, self.current)
        rows.append({'collected_at': (self.current + timedelta(hours=1)).isoformat(), 'value': 9999999})
        self.assertEqual(first, forecast_rows(rows, 24, self.current))
        self.assertGreater(first['backtest_targets'], 0)
        self.assertEqual(set(first['backtest_errors']), {'naive', 'damped'})

    def test_null_values_do_not_count_as_zero_or_coverage(self):
        rows = self.hourly(168)
        for row in rows[1:50]:
            row['value'] = None
        result = forecast_rows(rows, 24, self.current)
        self.assertFalse(result['available'])
        self.assertLess(result['coverage'], .8)

    def test_daily_forecast_has_seven_daily_points(self):
        rows = [{'source_time': (self.current - timedelta(days=27 - i)).date().isoformat(),
                 'collected_at': self.current.isoformat(), 'value': 100 + i} for i in range(28)]
        result = forecast_rows(rows, 168, self.current)
        self.assertTrue(result['available'])
        points = result['points']
        self.assertEqual(len(points), 7)
        self.assertEqual(datetime.fromisoformat(points[1]['time']) - datetime.fromisoformat(points[0]['time']), timedelta(days=1))


if __name__ == '__main__':
    unittest.main()
