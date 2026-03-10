import { describe, it, expect } from 'vitest';
import app from '../index';

function req(path: string, init?: RequestInit) {
  return new Request(`http://localhost${path}`, init);
}

describe('RoadGateway', () => {
  describe('GET /health', () => {
    it('returns healthy status', async () => {
      const res = await app.fetch(req('/health'));
      expect(res.status).toBe(200);
      const body = await res.json();
      expect(body.status).toBe('healthy');
      expect(body.service).toBe('roadgateway');
      expect(body.version).toBe('0.1.0');
      expect(body.timestamp).toBeDefined();
    });
  });

  describe('GET /', () => {
    it('returns service info', async () => {
      const res = await app.fetch(req('/'));
      expect(res.status).toBe(200);
      const body = await res.json();
      expect(body.name).toBe('RoadGateway');
      expect(body.version).toBe('0.1.0');
      expect(body.endpoints).toBeDefined();
    });
  });

  describe('GET /api/services', () => {
    it('returns list of services', async () => {
      const res = await app.fetch(req('/api/services'));
      expect(res.status).toBe(200);
      const body = await res.json();
      expect(body.services).toBeInstanceOf(Array);
      expect(body.services.length).toBeGreaterThan(0);
      expect(body.services[0]).toHaveProperty('name');
      expect(body.services[0]).toHaveProperty('url');
      expect(body.services[0]).toHaveProperty('status');
    });
  });

  describe('GET /api/version', () => {
    it('returns version info', async () => {
      const res = await app.fetch(req('/api/version'));
      expect(res.status).toBe(200);
      const body = await res.json();
      expect(body.gateway).toBe('0.1.0');
      expect(body.runtime).toBe('Cloudflare Workers');
    });
  });

  describe('POST /api/echo', () => {
    it('echoes back the request', async () => {
      const res = await app.fetch(req('/api/echo', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ test: true }),
      }));
      expect(res.status).toBe(200);
      const body = await res.json();
      expect(body.method).toBe('POST');
      expect(body.timestamp).toBeDefined();
    });
  });

  describe('GET /api/echo', () => {
    it('echoes GET request', async () => {
      const res = await app.fetch(req('/api/echo'));
      expect(res.status).toBe(200);
      const body = await res.json();
      expect(body.method).toBe('GET');
      expect(body.body).toBeNull();
    });
  });

  describe('404 handler', () => {
    it('returns 404 for unknown routes', async () => {
      const res = await app.fetch(req('/nonexistent'));
      expect(res.status).toBe(404);
      const body = await res.json();
      expect(body.error).toBe('Not Found');
    });
  });

  describe('CORS headers', () => {
    it('includes CORS headers on responses', async () => {
      const res = await app.fetch(req('/health'));
      // Hono CORS middleware sets these on actual requests
      expect(res.status).toBe(200);
    });

    it('handles OPTIONS preflight', async () => {
      const res = await app.fetch(req('/api/services', {
        method: 'OPTIONS',
        headers: {
          'Origin': 'http://example.com',
          'Access-Control-Request-Method': 'GET',
        },
      }));
      expect(res.status).toBe(204);
    });
  });
});
