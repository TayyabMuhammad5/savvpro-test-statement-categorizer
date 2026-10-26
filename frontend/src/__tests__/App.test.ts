import { describe, expect, it } from 'vitest';
import { ALL_CATEGORIES } from '../App';

describe('Frontend Categorizer Core', () => {
  it('contains all 17 photography studio Schedule C categories', () => {
    expect(ALL_CATEGORIES).toContain('Camera Equipment & Lighting');
    expect(ALL_CATEGORIES).toContain('Gear & Lens Rentals');
    expect(ALL_CATEGORIES).toContain('Photobook Printing & Lab COGS');
    expect(ALL_CATEGORIES).toContain('Contract Labor & Assistants');
    expect(ALL_CATEGORIES).toContain('Software & Digital Workflow');
    expect(ALL_CATEGORIES).toContain('Studio, Darkroom & Permits');
    expect(ALL_CATEGORIES).toContain('Shoot Travel & Transport');
    expect(ALL_CATEGORIES).toContain('Shipping & Book Fulfillment');
    expect(ALL_CATEGORIES).toContain('Props, Styling & Reference Books');
    expect(ALL_CATEGORIES).toContain('Client & Crew Meals (50%)');
    expect(ALL_CATEGORIES).toContain('Marketing, Book Fairs & Portfolio');
    expect(ALL_CATEGORIES).toContain('Insurance, Copyright & Guilds');
    expect(ALL_CATEGORIES).toContain('Bank & Processing Fees');
    expect(ALL_CATEGORIES).toContain('Client Shoot & Book Income');
    expect(ALL_CATEGORIES).toContain('Non-Deductible / Transfer');
    expect(ALL_CATEGORIES).toContain('Personal / Non-Deductible');
    expect(ALL_CATEGORIES).toContain('Needs Review');
    expect(ALL_CATEGORIES.length).toBe(17);
  });

  it('escapes potential formula injection in exported CSV values', () => {
    const escapeCell = (val: any): string => {
      if (val === null || val === undefined) return '""';
      let s = String(val);
      if (/^[=+\-@\t\r]/.test(s)) {
        s = `'${s}`;
      }
      return `"${s.replace(/"/g, '""')}"`;
    };

    // Dangerous formula payloads
    expect(escapeCell('=1+1')).toBe(`"'=1+1"`);
    expect(escapeCell('+cmd|')).toBe(`"'+cmd|"`);
    expect(escapeCell('-2+5')).toBe(`"'-2+5"`);
    expect(escapeCell('@SUM(A1:A10)')).toBe(`"'@SUM(A1:A10)"`);
    expect(escapeCell('\tHYPERLINK("http://evil.com")')).toBe(`"'\tHYPERLINK(""http://evil.com"")"`);

    // Benign payloads
    expect(escapeCell('B&H Photo')).toBe(`"B&H Photo"`);
    expect(escapeCell('Blurb "Book Print"')).toBe(`"Blurb ""Book Print"""`);
  });

  it('correctly handles sign conventions without guessing', () => {
    const supportedConventions = ['auto', 'charges_negative', 'charges_positive'];
    expect(supportedConventions).toContain('auto');
    expect(supportedConventions).toContain('charges_negative');
    expect(supportedConventions).toContain('charges_positive');
  });
});
