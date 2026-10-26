import http from 'k6/http';
import { check } from 'k6';

// Configurable target URL: defaults to local server, can be overridden via TARGET_URL env var
const BASE_URL = __ENV.TARGET_URL || 'http://127.0.0.1:8000';

export const options = {
  vus: __ENV.VUS ? parseInt(__ENV.VUS) : 20,
  duration: __ENV.DURATION || '10s', // Set -e DURATION=2m for full 2-minute soak
  thresholds: {
    http_req_failed: ['rate<0.01'],   // Error rate must be under 1%
    http_req_duration: ['p(95)<2000'], // 95% of requests must finish under 2000ms
  },
};

export default function () {
  const res = http.get(`${BASE_URL}/api/health`);
  check(res, {
    'status is 200': (r) => r.status === 200,
  });
}
