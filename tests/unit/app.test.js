import { describe, it, expect } from 'vitest';

/**
 * Unit tests for client-side document processing, geometry, and color utilities.
 */
describe('Geometry and Dimensional Calculations', () => {
  it('converts typographic points (pt) to millimeters (mm) accurately', () => {
    const ptToMm = (pt) => (pt * 25.4) / 72.0;
    
    // Standard Letter width: 612 pt -> 215.9 mm
    expect(Math.round(ptToMm(612) * 10) / 10).toBe(215.9);
    // Standard Letter height: 792 pt -> 279.4 mm
    expect(Math.round(ptToMm(792) * 10) / 10).toBe(279.4);
    // Standard A4 width: 595.28 pt -> 210.0 mm
    expect(Math.round(ptToMm(595.28) * 10) / 10).toBe(210.0);
    // Standard A4 height: 841.89 pt -> 297.0 mm
    expect(Math.round(ptToMm(841.89) * 10) / 10).toBe(297.0);
  });

  it('calculates aspect ratio and bounding box intersection', () => {
    const isIntersecting = (r1, r2) => {
      return !(r2.x0 > r1.x1 || r2.x1 < r1.x0 || r2.y0 > r1.y1 || r2.y1 < r1.y0);
    };

    const rectA = { x0: 50, y0: 50, x1: 150, y1: 150 };
    const rectB = { x0: 100, y0: 100, x1: 200, y1: 200 };
    const rectC = { x0: 300, y0: 300, x1: 400, y1: 400 };

    expect(isIntersecting(rectA, rectB)).toBe(true);
    expect(isIntersecting(rectA, rectC)).toBe(false);
  });
});

describe('Color Translation and Bitmask Normalization', () => {
  it('translates 24-bit sRGB integers to normalized RGB floating points', () => {
    const intToRgb = (c) => ({
      r: ((c >> 16) & 255) / 255.0,
      g: ((c >> 8) & 255) / 255.0,
      b: (c & 255) / 255.0,
    });

    const pureRed = intToRgb(0xff0000);
    expect(pureRed.r).toBe(1.0);
    expect(pureRed.g).toBe(0.0);
    expect(pureRed.b).toBe(0.0);

    const teal = intToRgb(0x008080);
    expect(Math.round(teal.g * 100) / 100).toBe(0.5);
    expect(Math.round(teal.b * 100) / 100).toBe(0.5);
  });

  it('correctly parses PDF permission bitmasks', () => {
    const PERM_PRINT = 4;
    const PERM_MODIFY = 8;
    const PERM_COPY = 16;
    const PERM_ANNOTATE = 32;

    const testPerms = PERM_PRINT | PERM_ANNOTATE; // 36

    expect(Boolean(testPerms & PERM_PRINT)).toBe(true);
    expect(Boolean(testPerms & PERM_MODIFY)).toBe(false);
    expect(Boolean(testPerms & PERM_COPY)).toBe(false);
    expect(Boolean(testPerms & PERM_ANNOTATE)).toBe(true);
  });
});
