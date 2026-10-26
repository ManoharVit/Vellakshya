import http from 'k6/http';
import { check, sleep } from 'k6';

// Minimal sample PDF payload for load testing
const SAMPLE_PDF = open('../test-data/sample-pdfs/sample.pdf', 'b');

export const options = {
  stages: [
    { duration: '5s', target: 5 },   // Ramp up to 5 concurrent users
    { duration: '10s', target: 10 },  // Sustained load with 10 users
    { duration: '3s', target: 0 },   // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<500'], // 95% of requests must complete within 500ms
    http_req_failed: ['rate<0.01'],    // Error rate must be under 1%
  },
};

export default function () {
  const BASE_URL = __ENV.TARGET_URL || 'http://127.0.0.1:8000';

  // 1. Web Page & Asset Delivery
  const resHome = http.get(`${BASE_URL}/`);
  check(resHome, {
    'Home status is 200': (r) => r.status === 200,
    'Home renders Vellakshya UI': (r) => r.body && r.body.includes('Vellakshya'),
  });

  // 2. High-Fidelity PDF to HTML Conversion
  const payload = {
    file: http.file(SAMPLE_PDF, 'sample.pdf', 'application/pdf'),
    mode: 'fixed',
  };
  const resConvert = http.post(`${BASE_URL}/api/convert/html`, payload);
  check(resConvert, {
    'Conversion status is 200': (r) => r.status === 200,
    'Conversion returns HTML': (r) => r.headers['Content-Type'] && r.headers['Content-Type'].includes('text/html'),
  });

  // 3. Deep Document Inspection
  const resInspect = http.post(`${BASE_URL}/api/inspect`, {
    file: http.file(SAMPLE_PDF, 'sample.pdf', 'application/pdf'),
  });
  check(resInspect, {
    'Inspection status is 200': (r) => r.status === 200,
    'Inspection returns metadata': (r) => r.json('page_count') > 0,
  });

  sleep(0.5);
}
