// C-30: exercise the runtime packages after the security updates.
/* global global, require, test, expect */
import axios from 'axios';
import { TextEncoder, TextDecoder } from 'util';
import { z } from 'zod';

// Jest 27's jsdom lacks these browser APIs. Exercise the router core directly;
// the production build separately verifies react-router-dom's package exports.
global.TextEncoder ??= TextEncoder;
global.TextDecoder ??= TextDecoder;
const { matchRoutes } = require('react-router');

test('axios preserves the API method, URL and authorization header', async () => {
  let sent;
  const api = axios.create({ baseURL: 'https://crm.example.com/api', adapter: async config => {
    sent = config;
    return { data: { ok: true }, status: 200, statusText: 'OK', headers: {}, config };
  } });
  const result = await api.patch('/tasks/task-1', { status: 'done' }, {
    headers: { Authorization: 'Bearer test-only' },
  });
  expect(result.data).toEqual({ ok: true });
  expect(sent.method).toBe('patch');
  expect(sent.url).toBe('/tasks/task-1');
  expect(sent.headers.get('Authorization')).toBe('Bearer test-only');
  expect(JSON.parse(sent.data)).toEqual({ status: 'done' });
});

test('router still matches a nested record URL and rejects unknown paths', () => {
  const routes = [{ path: '/contacts', children: [{ path: ':id' }] }];
  expect(matchRoutes(routes, '/contacts/contact-123')[1].params.id).toBe('contact-123');
  expect(matchRoutes(routes, '/unknown')).toBeNull();
});

test('zod bounds a collection and returns structured validation errors', () => {
  const schema = z.array(z.object({ email: z.string().email() })).max(2);
  expect(schema.safeParse([{ email: 'person@example.com' }]).success).toBe(true);
  const oversized = schema.safeParse(Array(3).fill({ email: 'person@example.com' }));
  expect(oversized.success).toBe(false);
  expect(oversized.error.issues.some(issue => issue.code === 'too_big')).toBe(true);
  expect(schema.safeParse([{ email: 'invalid' }]).success).toBe(false);
});
