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
});
