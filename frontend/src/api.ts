import { SamplePreset, StatementAnalysisResponse } from './types';

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api';

export async function fetchPresets(): Promise<SamplePreset[]> {
  const res = await fetch(`${API_BASE}/presets`);
  if (!res.ok) {
    throw new Error(`Failed to fetch presets: ${res.status}`);
  }
  return res.json();
}

export async function analyzeStatement(
  statementName: string,
  csvContent: string,
  customRules: Record<string, string>
): Promise<StatementAnalysisResponse> {
  const res = await fetch(`${API_BASE}/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      statement_name: statementName,
      csv_content: csvContent,
      custom_rules: customRules,
    }),
  });
  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`Statement analysis failed: ${errText}`);
  }
  return res.json();
}
