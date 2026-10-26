import { test, expect } from '@playwright/test';
import fs from 'fs';
import path from 'path';

const SAMPLE_PDF_PATH = path.resolve(__dirname, '../../test-data/sample-pdfs/sample.pdf');
const POLYGLOT_PATH = path.resolve(__dirname, '../../test-data/malicious-files/polyglot.gif.pdf');

test.describe('Vellakshya REST API Contract Tests', () => {
  test('POST /api/inspect returns preflight metadata and statistics', async ({ request }) => {
    const fileBuffer = fs.readFileSync(SAMPLE_PDF_PATH);
    const response = await request.post('/api/inspect', {
      multipart: {
        file: {
          name: 'sample.pdf',
          mimeType: 'application/pdf',
          buffer: fileBuffer,
        },
      },
    });

    expect(response.status()).toBe(200);
    const data = await response.json();
    expect(data.page_count).toBe(1);
    expect(data.metadata.title).toBe('Vellakshya Master Sample');
    expect(data.metadata.author).toBe('Giri Manohar Vemula');
    expect(data.permissions).toBeDefined();
    expect(data.stats.total_words).toBeGreaterThan(0);
  });

  test('POST /api/convert/html converts PDF to semantic HTML', async ({ request }) => {
    const fileBuffer = fs.readFileSync(SAMPLE_PDF_PATH);
    const response = await request.post('/api/convert/html', {
      multipart: {
        file: {
          name: 'sample.pdf',
          mimeType: 'application/pdf',
          buffer: fileBuffer,
        },
        mode: 'semantic',
      },
    });

    expect(response.status()).toBe(200);
    expect(response.headers()['content-type']).toContain('text/html');
    const html = await response.text();
    expect(html).toContain('Vellakshya Enterprise Document Engine');
    expect(html).toContain('https://github.com/ManoharVit/Vellakshya');
  });

  test('POST /api/signatures/sign and /api/signatures/verify detect tamper', async ({ request }) => {
    const fileBuffer = fs.readFileSync(SAMPLE_PDF_PATH);
    
    // 1. Sign
    const signRes = await request.post('/api/signatures/sign', {
      multipart: {
        file: {
          name: 'sample.pdf',
          mimeType: 'application/pdf',
          buffer: fileBuffer,
        },
        signer_name: 'Lead Architect Giri Manohar Vemula',
        reason: 'Contract Ratification',
      },
    });
    expect(signRes.status()).toBe(200);
    const signedPdf = await signRes.body();

    // 2. Verify clean signed document
    const verifyCleanRes = await request.post('/api/signatures/verify', {
      multipart: {
        file: {
          name: 'signed.pdf',
          mimeType: 'application/pdf',
          buffer: signedPdf,
        },
      },
    });
    expect(verifyCleanRes.status()).toBe(200);
    const cleanData = await verifyCleanRes.json();
    expect(cleanData.has_signature).toBe(true);
    expect(cleanData.is_valid).toBe(true);
    expect(cleanData.status).toBe('VALID_SIGNATURE');
  });

  test('POST /api/security/validate safely rejects polyglot files', async ({ request }) => {
    const polyglotBuffer = fs.readFileSync(POLYGLOT_PATH);
    const response = await request.post('/api/security/validate', {
      multipart: {
        file: {
          name: 'exploit.gif.pdf',
          mimeType: 'application/pdf',
          buffer: polyglotBuffer,
        },
      },
    });

    expect(response.status()).toBe(400);
    const data = await response.json();
    expect(data.detail.safe).toBe(false);
    expect(data.detail.error_type).toBe('INVALID_HEADER_POLYGLOT');
  });

  test('POST /api/auth lifecycle: register, login, store document, delete, and assert 404', async ({ request }) => {
    const email = `playwright_${Date.now()}@vellakshya.io`;
    const password = 'PlaywrightSecure123!';

    // 1. Register
    const regRes = await request.post('/api/auth/register', {
      data: { email, password, role: 'editor' },
    });
    expect(regRes.status()).toBe(200);

    // 2. Login
    const loginRes = await request.post('/api/auth/login', {
      data: { email, password },
    });
    expect(loginRes.status()).toBe(200);
    const { token } = await loginRes.json();
    expect(token).toBeDefined();

    // 3. Store document
    const fileBuffer = fs.readFileSync(SAMPLE_PDF_PATH);
    const docRes = await request.post('/api/documents', {
      headers: { Authorization: `Bearer ${token}` },
      multipart: {
        file: {
          name: 'sample.pdf',
          mimeType: 'application/pdf',
          buffer: fileBuffer,
        },
      },
    });
    expect(docRes.status()).toBe(200);
    const { doc_id } = await docRes.json();
    expect(doc_id).toBeDefined();

    // 4. Retrieve document
    const getRes = await request.get(`/api/documents/${doc_id}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(getRes.status()).toBe(200);

    // 5. Delete document
    const delRes = await request.delete(`/api/documents/${doc_id}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(delRes.status()).toBe(200);

    // 6. Direct URL now returns 404
    const notFoundRes = await request.get(`/api/documents/${doc_id}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(notFoundRes.status()).toBe(404);

    // 7. Logout
    const logoutRes = await request.post('/api/auth/logout', {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(logoutRes.status()).toBe(200);
  });
});
