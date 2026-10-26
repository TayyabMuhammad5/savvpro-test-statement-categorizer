import { APIError, RowDecision, SamplePreset, StatementAnalysisResponse } from './types';

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api';

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let errorObj: APIError;
    try {
      errorObj = await res.json();
    } catch {
      const text = await res.text();
      errorObj = {
        code: `HTTP_${res.status}`,
        message: text || res.statusText,
      };
    }
    const message = errorObj.message || `API Error (${res.status})`;
    const error = new Error(message) as Error & { code?: string; details?: any };
    error.code = errorObj.code;
    error.details = errorObj.details;
    throw error;
  }
  return res.json();
}

export async function fetchPresets(): Promise<SamplePreset[]> {
  const res = await fetch(`${API_BASE}/presets`);
  return handleResponse<SamplePreset[]>(res);
}

export async function analyzeStatement(
  statementName: string,
  csvContent: string,
  customRules: Record<string, string> = {},
  rowDecisions: Record<string, RowDecision> = {},
  signConvention: string = 'auto'
): Promise<StatementAnalysisResponse> {
  const res = await fetch(`${API_BASE}/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      statement_name: statementName,
      csv_content: csvContent,
      custom_rules: customRules,
      row_decisions: rowDecisions,
      sign_convention: signConvention,
    }),
  });
  return handleResponse<StatementAnalysisResponse>(res);
}

export async function uploadStatementFile(
  file: File,
  customRules: Record<string, string> = {},
  rowDecisions: Record<string, RowDecision> = {},
  signConvention: string = 'auto'
): Promise<StatementAnalysisResponse> {
  const formData = new FormData();
  formData.append('file', file);
  if (Object.keys(customRules).length > 0) {
    formData.append('custom_rules', JSON.stringify(customRules));
  }
  if (Object.keys(rowDecisions).length > 0) {
    formData.append('row_decisions', JSON.stringify(rowDecisions));
  }
  formData.append('sign_convention', signConvention);

  const res = await fetch(`${API_BASE}/upload`, {
    method: 'POST',
    body: formData,
  });
  return handleResponse<StatementAnalysisResponse>(res);
}
