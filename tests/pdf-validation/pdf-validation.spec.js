import { test, expect } from '@playwright/test';
import { PDFDocument } from 'pdf-lib';
import fs from 'fs';
import path from 'path';

const SAMPLE_PDF_PATH = path.resolve(__dirname, '../../test-data/sample-pdfs/sample.pdf');
const MULTICOLUMN_PDF_PATH = path.resolve(__dirname, '../../test-data/sample-pdfs/multicolumn.pdf');

test.describe('Structural PDF Validation via pdf-lib and pdf.js', () => {
  test('validates master sample PDF structure, page count and metadata', async () => {
    const pdfBytes = fs.readFileSync(SAMPLE_PDF_PATH);
    const pdfDoc = await PDFDocument.load(pdfBytes);

    expect(pdfDoc.getPageCount()).toBe(1);
    expect(pdfDoc.getTitle()).toBe('Vellakshya Master Sample');
    expect(pdfDoc.getAuthor()).toBe('Giri Manohar Vemula');

    const page1 = pdfDoc.getPage(0);
    const { width, height } = page1.getSize();
    expect(width).toBe(612);
    expect(height).toBe(792);
  });

  test('validates multi-column PDF page tree and modification stability', async () => {
    const pdfBytes = fs.readFileSync(MULTICOLUMN_PDF_PATH);
    const pdfDoc = await PDFDocument.load(pdfBytes);

    expect(pdfDoc.getPageCount()).toBe(1);

    // Perform an in-memory modification: add a page and re-save
    pdfDoc.addPage([612, 792]);
    expect(pdfDoc.getPageCount()).toBe(2);

    const savedBytes = await pdfDoc.save();
    expect(savedBytes.length).toBeGreaterThan(pdfBytes.length);

    // Reload and verify persistence
    const reloaded = await PDFDocument.load(savedBytes);
    expect(reloaded.getPageCount()).toBe(2);
  });
});
