/** Presentation rules shared by the overview, source details and trend analysis. */
export const isRank = (metric: string) => metric === 'rank' || metric.endsWith('_rank');
export const resetsDaily = (metric: string) => metric === 'maoyan_heat_snapshot' || metric.startsWith('dengta_');

export function formatValue(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '暂无数据';
  const size = Math.abs(value);
  const format = (n: number) => n.toLocaleString('zh-CN', {maximumFractionDigits: 2});
  if (size >= 1e8) return format(value / 1e8) + '亿';
  if (size >= 1e4) return format(value / 1e4) + '万';
  return format(value);
}

export function beijingStamp(value: string): number {
  return Date.parse(value.length === 10 ? value + 'T00:00:00+08:00' : value);
}

/** Zero selects the Beijing calendar day; positive values select rolling hours. */
export function timeWindow(hours: number, end = Date.now()) {
  const offset = 8 * 3600000;
  const midnight = Math.floor((end + offset) / 86400000) * 86400000 - offset;
  return {start: hours === 0 ? midnight : end - hours * 3600000, end};
}

export function queryHoursFor(window: {start: number; end: number}) {
  return Math.max(1, Math.ceil((window.end - window.start) / 3600000));
}

export function measurementTime(value?: string): string {
  if (!value) return '暂无统计时间';
  if (value.length === 10) return value.replace(/-/g, '/');
  return new Date(value).toLocaleString('zh-CN', {timeZone: 'Asia/Shanghai', hour12: false});
}

type Observation = {
  value: number | null;
  time: string;
  unit: string;
  metadata?: Record<string, unknown>;
};

export function seriesSummary(rows: Observation[], metric: string) {
  let samples = rows.filter(p => p.value != null && Number.isFinite(p.value))
    .sort((a, b) => beijingStamp(a.time) - beijingStamp(b.time));
  // A cat-eye snapshot resets each statistical day; cross-day changes are meaningless.
  if (resetsDaily(metric) && samples.length) {
    const day = samples[samples.length - 1].metadata?.statistical_date;
    samples = samples.filter(p => p.metadata?.statistical_date === day);
  }
  const rank = isRank(metric);
  const units = new Set(samples.map(p => p.unit));
  const scopes = new Set(samples.map(p => String(p.metadata?.scope || '')));
  const consistent = units.size <= 1 && scopes.size <= 1;
  const first = samples[0];
  const last = samples[samples.length - 1];
  const delta = consistent && samples.length > 1 ? last.value! - first.value! : null;
  const percentagePoints = first?.unit === '%';
  const growth = delta != null && !rank && !percentagePoints && first.value !== 0
    ? delta / Math.abs(first.value!) * 100 : null;
  const values = samples.map(p => p.value!);
  const peak = values.length && consistent ? (rank ? Math.min(...values) : Math.max(...values)) : null;
  const maxStep = delta != null ? Math.max(...values.slice(1).map((v, i) => Math.abs(v - values[i]))) : null;
  const change = delta == null ? '样本不足' : rank
    ? delta === 0 ? '排名不变' : `${delta < 0 ? '上升' : '下降'} ${Math.abs(delta)} 位`
    : `${delta > 0 ? '+' : ''}${formatValue(delta)}${percentagePoints ? ' 个百分点' : ' ' + (first?.unit || '')}`;
  return {
    count: samples.length, first, last, delta, growth, peak, maxStep, rank, percentagePoints,
    change: consistent ? change : '口径变化，暂停计算', consistent,
    scopeNote: resetsDaily(metric) ? '仅计算最新统计日内的变化' : '按所选时段的首末实际记录计算',
  };
}
