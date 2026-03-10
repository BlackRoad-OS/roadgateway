import { describe, it, expect, beforeEach } from 'vitest';
import { MetricsCollector } from '../metrics';

describe('MetricsCollector', () => {
  let collector: MetricsCollector;

  beforeEach(() => {
    collector = new MetricsCollector();
  });

  it('records and aggregates metrics', () => {
    collector.record({
      path: '/api/test',
      method: 'GET',
      statusCode: 200,
      latencyMs: 50,
      timestamp: Date.now(),
      cached: false,
    });

    collector.record({
      path: '/api/test',
      method: 'GET',
      statusCode: 200,
      latencyMs: 100,
      timestamp: Date.now(),
      cached: false,
    });

    const metrics = collector.getAggregated(5);
    expect(metrics.requests.total).toBe(2);
    expect(metrics.requests.success).toBe(2);
    expect(metrics.requests.errors).toBe(0);
    expect(metrics.latency.avg).toBe(75);
  });

  it('counts errors correctly', () => {
    collector.record({
      path: '/api/fail',
      method: 'GET',
      statusCode: 500,
      latencyMs: 10,
      timestamp: Date.now(),
      cached: false,
    });

    const metrics = collector.getAggregated(5);
    expect(metrics.requests.errors).toBe(1);
    expect(metrics.requests.success).toBe(0);
  });

  it('tracks rate limited requests', () => {
    collector.record({
      path: '/api/test',
      method: 'GET',
      statusCode: 429,
      latencyMs: 5,
      timestamp: Date.now(),
      cached: false,
    });

    const metrics = collector.getAggregated(5);
    expect(metrics.rateLimit.limited).toBe(1);
  });

  it('returns empty metrics when no data', () => {
    const metrics = collector.getAggregated(5);
    expect(metrics.requests.total).toBe(0);
    expect(metrics.latency.avg).toBe(0);
  });

  it('clears metrics', () => {
    collector.record({
      path: '/test',
      method: 'GET',
      statusCode: 200,
      latencyMs: 10,
      timestamp: Date.now(),
      cached: false,
    });

    collector.clear();
    const metrics = collector.getAggregated(5);
    expect(metrics.requests.total).toBe(0);
  });

  it('trims old metrics beyond max', () => {
    const small = new MetricsCollector(5);
    for (let i = 0; i < 10; i++) {
      small.record({
        path: `/api/${i}`,
        method: 'GET',
        statusCode: 200,
        latencyMs: i * 10,
        timestamp: Date.now(),
        cached: false,
      });
    }

    const metrics = small.getAggregated(5);
    expect(metrics.requests.total).toBe(5);
  });

  it('exports Prometheus format', () => {
    collector.record({
      path: '/api/test',
      method: 'GET',
      statusCode: 200,
      latencyMs: 42,
      timestamp: Date.now(),
      cached: false,
    });

    const prom = collector.toPrometheus();
    expect(prom).toContain('gateway_requests_total 1');
    expect(prom).toContain('gateway_errors_total 0');
    expect(prom).toContain('gateway_latency_ms');
  });

  it('tracks metrics by path', () => {
    collector.record({
      path: '/api/a',
      method: 'GET',
      statusCode: 200,
      latencyMs: 10,
      timestamp: Date.now(),
      cached: false,
    });
    collector.record({
      path: '/api/b',
      method: 'GET',
      statusCode: 200,
      latencyMs: 20,
      timestamp: Date.now(),
      cached: false,
    });

    const metrics = collector.getAggregated(5);
    expect(Object.keys(metrics.byPath)).toHaveLength(2);
    expect(metrics.byPath['/api/a'].count).toBe(1);
    expect(metrics.byPath['/api/b'].count).toBe(1);
  });

  it('gets top paths', () => {
    for (let i = 0; i < 5; i++) {
      collector.record({
        path: '/api/popular',
        method: 'GET',
        statusCode: 200,
        latencyMs: 10,
        timestamp: Date.now(),
        cached: false,
      });
    }
    collector.record({
      path: '/api/rare',
      method: 'GET',
      statusCode: 200,
      latencyMs: 10,
      timestamp: Date.now(),
      cached: false,
    });

    const top = collector.getTopPaths(1);
    expect(top[0].path).toBe('/api/popular');
    expect(top[0].count).toBe(5);
  });

  it('gets time series data', () => {
    collector.record({
      path: '/api/test',
      method: 'GET',
      statusCode: 200,
      latencyMs: 10,
      timestamp: Date.now(),
      cached: false,
    });

    const series = collector.getTimeSeries(60, 1);
    expect(series.length).toBeGreaterThan(0);
    expect(series[0].requests).toBe(1);
  });
});
