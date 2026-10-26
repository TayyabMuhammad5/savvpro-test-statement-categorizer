import React, { useEffect, useMemo, useState, useCallback } from 'react';
import {
  AlertCircle,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Download,
  FileSpreadsheet,
  Info,
  Layers,
  RotateCcw,
  Search,
  ShieldAlert,
  Tag,
  Upload,
  X,
} from 'lucide-react';
import { analyzeStatement, fetchPresets } from './api';
import {
  CategorizedTransaction,
  RowDecision,
  SamplePreset,
  StatementAnalysisResponse,
} from './types';

export const ALL_CATEGORIES = [
  'Camera Equipment & Lighting',
  'Gear & Lens Rentals',
  'Photobook Printing & Lab COGS',
  'Contract Labor & Assistants',
  'Software & Digital Workflow',
  'Studio, Darkroom & Permits',
  'Shoot Travel & Transport',
  'Shipping & Book Fulfillment',
  'Props, Styling & Reference Books',
  'Client & Crew Meals (50%)',
  'Marketing, Book Fairs & Portfolio',
  'Insurance, Copyright & Guilds',
  'Bank & Processing Fees',
  'Client Shoot & Book Income',
  'Non-Deductible / Transfer',
  'Personal / Non-Deductible',
  'Needs Review',
];

function friendlyVendorName(norm: string, raw: string): string {
  const base = norm || raw || '';
  return base
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .replace(/\bBh\b/g, 'B&H')
    .replace(/\bB&h\b/g, 'B&H')
    .replace(/\bUsps\b/g, 'USPS')
    .replace(/\bIsbn\b/g, 'ISBN')
    .replace(/\bNy\b/g, 'NY')
    .replace(/\bCa\b/g, 'CA');
}

export default function App() {
  const [presets, setPresets] = useState<SamplePreset[]>([]);
  const [selectedPresetId, setSelectedPresetId] = useState<string>('chase_studio_card');
  const [statementName, setStatementName] = useState<string>('chase_studio_credit_card_2025.csv');
  const [csvContent, setCsvContent] = useState<string>('');
  const [signConvention, setSignConvention] = useState<string>('auto');
  const [customRules, setCustomRules] = useState<Record<string, string>>({});
  const [rowDecisions, setRowDecisions] = useState<Record<string, RowDecision>>({});
  const [history, setHistory] = useState<{ rules: Record<string, string>; decisions: Record<string, RowDecision> }[]>([]);
  const [analysis, setAnalysis] = useState<StatementAnalysisResponse | null>(null);
  const [activeView, setActiveView] = useState<'transactions' | 'categories'>('transactions');
  const [filterMode, setFilterMode] = useState<'all' | 'needs_review' | 'refunds' | 'transfers' | 'section179'>('all');
  const [categoryFilter, setCategoryFilter] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [drawerTxId, setDrawerTxId] = useState<string | null>(null);
  const [reviewCursor, setReviewCursor] = useState<number>(0);
  const [rememberVendor, setRememberVendor] = useState<boolean>(true);
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [switcherOpen, setSwitcherOpen] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchPresets()
      .then((list) => {
        setPresets(list);
        if (list.length > 0) {
          setSelectedPresetId(list[0].id);
          setStatementName(list[0].filename);
          setCsvContent(list[0].csv);
        }
      })
      .catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    if (!csvContent.trim()) return;
    setError(null);
    analyzeStatement(statementName, csvContent, customRules, rowDecisions, signConvention)
      .then((res) => setAnalysis(res))
      .catch((err) => setError(err.message));
  }, [csvContent, statementName, customRules, rowDecisions, signConvention]);

  const handlePresetChange = (presetId: string) => {
    const found = presets.find((p) => p.id === presetId);
    if (!found) return;
    setSelectedPresetId(found.id);
    setStatementName(found.filename);
    setCsvContent(found.csv);
    setCustomRules({});
    setRowDecisions({});
    setHistory([]);
    setReviewCursor(0);
    setDrawerTxId(null);
    setSwitcherOpen(false);
    setError(null);
  };

  const processUploadedFile = (file: File) => {
    if (file.size > 5 * 1024 * 1024) {
      setError(`File size (${(file.size / 1024 / 1024).toFixed(2)} MB) exceeds 5 MB limit.`);
      return;
    }
    const reader = new FileReader();
    reader.onload = (ev) => {
      const text = String(ev.target?.result || '');
      const lineCount = text.split('\n').length;
      if (lineCount > 20000) {
        setError(`Statement contains ~${lineCount.toLocaleString()} rows, exceeding the 20,000 row limit.`);
        return;
      }
      setStatementName(file.name);
      setCsvContent(text);
      setSelectedPresetId('custom');
      setCustomRules({});
      setRowDecisions({});
      setHistory([]);
      setReviewCursor(0);
      setDrawerTxId(null);
      setSwitcherOpen(false);
      setError(null);
    };
    reader.readAsText(file);
  };

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) processUploadedFile(file);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) processUploadedFile(file);
  };

  const handleAssignCategory = useCallback(
    (tx: CategorizedTransaction, newCategory: string) => {
      setHistory((prev) => [...prev, { rules: { ...customRules }, decisions: { ...rowDecisions } }]);

      if (rememberVendor) {
        const key = tx.normalized_merchant || tx.raw_description;
        setCustomRules((prev) => ({
          ...prev,
          [key]: newCategory,
        }));
      } else {
        const rowKey = `tx-${tx.row_index}`;
        setRowDecisions((prev) => ({
          ...prev,
          [rowKey]: {
            action: 'categorize',
            category: newCategory,
            confirm_income_on_outflow: tx.amount < 0 && newCategory === 'Client Shoot & Book Income',
          },
        }));
      }
    },
    [rememberVendor, customRules, rowDecisions]
  );

  const handleExcludeRow = useCallback(
    (tx: CategorizedTransaction) => {
      setHistory((prev) => [...prev, { rules: { ...customRules }, decisions: { ...rowDecisions } }]);
      const rowKey = `tx-${tx.row_index}`;
      setRowDecisions((prev) => ({
        ...prev,
        [rowKey]: { action: 'exclude' },
      }));
    },
    [customRules, rowDecisions]
  );

  const handleUndo = useCallback(() => {
    if (history.length === 0) return;
    const previous = history[history.length - 1];
    setCustomRules(previous.rules);
    setRowDecisions(previous.decisions);
    setHistory((prev) => prev.slice(0, prev.length - 1));
  }, [history]);

  const reviewQueue = useMemo(() => {
    if (!analysis) return [];
    return analysis.transactions.filter((t) => t.needs_review);
  }, [analysis]);

  const activeReviewTx = reviewQueue.length > 0 ? reviewQueue[reviewCursor % reviewQueue.length] : null;

  const handleSkip = useCallback(() => {
    if (reviewQueue.length > 0) {
      setReviewCursor((prev) => (prev + 1) % reviewQueue.length);
    }
  }, [reviewQueue.length]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName?.toLowerCase();
      if (tag === 'input' || tag === 'select' || tag === 'textarea') return;

      if (!activeReviewTx) return;

      if (e.key === '1' && activeReviewTx.suggested_categories[0]) {
        e.preventDefault();
        handleAssignCategory(activeReviewTx, activeReviewTx.suggested_categories[0]);
      } else if (e.key === '2' && activeReviewTx.suggested_categories[1]) {
        e.preventDefault();
        handleAssignCategory(activeReviewTx, activeReviewTx.suggested_categories[1]);
      } else if (e.key === '3' && activeReviewTx.suggested_categories[2]) {
        e.preventDefault();
        handleAssignCategory(activeReviewTx, activeReviewTx.suggested_categories[2]);
      } else if (e.key === 's' || e.key === 'S') {
        e.preventDefault();
        handleSkip();
      } else if ((e.key === 'u' || e.key === 'U') && history.length > 0) {
        e.preventDefault();
        handleUndo();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [activeReviewTx, handleAssignCategory, handleSkip, handleUndo, history.length]);

  const filteredTransactions = useMemo(() => {
    if (!analysis) return [];
    return analysis.transactions.filter((tx) => {
      if (filterMode === 'needs_review' && !tx.needs_review) return false;
      if (filterMode === 'refunds' && tx.transaction_type !== 'refund') return false;
      if (
        filterMode === 'transfers' &&
        tx.transaction_type !== 'transfer' &&
        tx.transaction_type !== 'duplicate' &&
        tx.transaction_type !== 'excluded'
      )
        return false;
      if (filterMode === 'section179' && tx.tax_flag !== 'SECTION_179_CANDIDATE') return false;
      if (categoryFilter !== 'ALL' && tx.category !== categoryFilter) return false;
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        return (
          tx.raw_description.toLowerCase().includes(q) ||
          tx.normalized_merchant.toLowerCase().includes(q) ||
          tx.category.toLowerCase().includes(q) ||
          tx.matched_rule.toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [analysis, filterMode, categoryFilter, searchQuery]);

  const drawerTx = useMemo(() => {
    if (!analysis || !drawerTxId) return null;
    return analysis.transactions.find((t) => t.id === drawerTxId) || null;
  }, [analysis, drawerTxId]);

  const activePresetLabel = useMemo(() => {
    const found = presets.find((p) => p.id === selectedPresetId);
    return found ? found.name : statementName;
  }, [presets, selectedPresetId, statementName]);

  const exportScheduleCCsv = () => {
    if (!analysis) return;
    const headers = [
      'Row',
      'Date',
      'Description',
      'Normalized_Merchant',
      'Signed_Amount',
      'Transaction_Type',
      'Category',
      'Schedule_C_Line',
      'Deductible_Rate',
      'Deductible_Impact',
      'Confidence',
      'Needs_Review',
      'Tax_Flag',
      'Matched_Rule',
      'Tax_Notes',
    ];

    const escapeCell = (val: unknown): string => {
      if (val === null || val === undefined) return '""';
      let s = String(val);
      if (/^[=+\-@\t\r]/.test(s)) {
        s = `'${s}`;
      }
      return `"${s.replace(/"/g, '""')}"`;
    };

    const rows = analysis.transactions.map((t) => [
      t.row_index,
      escapeCell(t.date),
      escapeCell(t.raw_description),
      escapeCell(t.normalized_merchant),
      t.amount.toFixed(2),
      escapeCell(t.transaction_type),
      escapeCell(t.category),
      escapeCell(t.category === 'Needs Review' ? 'Unassigned' : 'Line 1 - 27a'),
      t.deductible_rate,
      t.deductible_impact.toFixed(2),
      t.confidence.toFixed(2),
      t.needs_review,
      escapeCell(t.tax_flag),
      escapeCell(t.matched_rule),
      escapeCell(t.tax_note || ''),
    ]);

    const csvBlob = [headers.join(','), ...rows.map((r) => r.join(','))].join('\r\n');
    const blob = new Blob([csvBlob], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `categorized_${statementName.replace(/\.csv$/i, '')}_schedule_c.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div
      className="min-h-screen bg-[#F3EFE6] text-[#141311] pb-32 selection:bg-[#FF4F17]/15"
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Drag & Drop Open Overlay */}
      {isDragging && (
        <div className="fixed inset-0 z-50 bg-[#141311]/75 backdrop-blur-sm flex flex-col items-center justify-center text-[#F3EFE6] pointer-events-none">
          <Upload className="w-14 h-14 text-[#FF4F17] animate-bounce mb-4" />
          <h2 className="font-serif text-4xl italic">Drop CSV Statement to Sort</h2>
          <p className="text-xs font-mono uppercase tracking-widest text-[#F3EFE6]/70 mt-2">
            100% Deterministic Rule Engine &bull; Zero-LLM
          </p>
        </div>
      )}

      {/* ULTRA-MINIMAL 2-CLUSTER OPEN HEADER (Zero Clutter, Zero Boxes) */}
      <header className="max-w-5xl mx-auto px-6 pt-8 pb-5 flex items-center justify-between border-b border-[#141311]/10">
        <div className="flex items-center gap-3">
          <span className="w-3 h-3 rounded-full bg-[#FF4F17] inline-block" />
          <span className="font-serif text-2xl tracking-tight text-[#141311]">
            Focal <span className="italic font-normal">&amp;</span> Folio
          </span>
          <span className="hidden sm:inline-block text-[10px] font-mono uppercase tracking-[0.2em] text-[#635E54] ml-2">
            01 // Tax Ledger
          </span>
        </div>

        <div className="flex items-center gap-5 relative">
          {/* Compact Statement Switcher Trigger */}
          <button
            type="button"
            onClick={() => setSwitcherOpen((o) => !o)}
            className="flex items-center gap-2 text-xs font-mono text-[#635E54] hover:text-[#141311] transition cursor-pointer"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-[#12734C]" />
            <span>{activePresetLabel}</span>
            <ChevronDown className="w-3.5 h-3.5 opacity-60" />
          </button>

          <button
            type="button"
            onClick={exportScheduleCCsv}
            className="magnetic-pill px-4 py-1.5 rounded-full bg-[#141311] hover:bg-[#FF4F17] text-[#F3EFE6] text-xs font-medium tracking-wide cursor-pointer flex items-center gap-1.5"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Export Schedule C</span>
          </button>

          {/* Floating Statement Switcher & Upload Popover */}
          {switcherOpen && (
            <div className="animate-stage absolute right-0 top-10 z-50 w-80 bg-[#141311] text-[#F3EFE6] rounded-2xl p-4 shadow-2xl">
              <div className="flex items-center justify-between pb-2.5 mb-2.5 border-b border-white/10">
                <span className="text-[10px] font-mono uppercase tracking-[0.18em] text-white/50">
                  Select Statement Source
                </span>
                <button
                  type="button"
                  onClick={() => setSwitcherOpen(false)}
                  className="text-white/50 hover:text-white text-xs cursor-pointer"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>

              <div className="space-y-1 max-h-60 overflow-y-auto pr-1">
                {presets.map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => handlePresetChange(p.id)}
                    className={`w-full text-left px-3 py-2 rounded-xl transition flex items-center justify-between cursor-pointer ${
                      selectedPresetId === p.id ? 'bg-white/10 text-white' : 'text-white/65 hover:bg-white/5 hover:text-white'
                    }`}
                  >
                    <div>
                      <div className="text-xs font-medium">{p.name}</div>
                      <div className="text-[10px] font-mono text-white/45 truncate max-w-[210px]">{p.filename}</div>
                    </div>
                    {selectedPresetId === p.id && <span className="w-2 h-2 rounded-full bg-[#FF4F17]" />}
                  </button>
                ))}
              </div>

              <div className="mt-3 pt-3 border-t border-white/10 space-y-2.5">
                <div className="flex items-center justify-between text-[11px] font-mono text-white/60 px-1">
                  <span>Sign Polarity:</span>
                  <select
                    value={signConvention}
                    onChange={(e) => setSignConvention(e.target.value)}
                    className="bg-white/10 text-white rounded px-2 py-0.5 text-[11px] font-mono focus:outline-none cursor-pointer"
                  >
                    <option value="auto" className="text-black">Auto Detect</option>
                    <option value="charges_negative" className="text-black">Charges Negative (-)</option>
                    <option value="charges_positive" className="text-black">Charges Positive (+)</option>
                  </select>
                </div>

                <label className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-xl bg-[#FF4F17] hover:bg-[#e04310] text-white text-xs font-medium transition cursor-pointer">
                  <Upload className="w-3.5 h-3.5" />
                  <span>Upload Custom Bank CSV</span>
                  <input type="file" accept=".csv" className="hidden" onChange={handleFileInputChange} />
                </label>
              </div>
            </div>
          )}
        </div>
      </header>

      {/* MAIN OPEN-CANVAS WORKSPACE */}
      <main className="max-w-5xl mx-auto px-6 pt-10">
        {/* Inline Error Line (No Box) */}
        {error && (
          <div className="pb-6 mb-6 border-b border-red-500/30 text-red-700 text-xs font-mono flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Inline Parse Warnings (No Box) */}
        {analysis && analysis.parse_warnings.length > 0 && (
          <div className="pb-4 mb-6 border-b border-[#141311]/10 text-amber-800 text-xs font-mono flex items-center gap-2">
            <Info className="w-3.5 h-3.5 shrink-0" />
            <span>{analysis.parse_warnings.join(' · ')}</span>
          </div>
        )}

        {analysis && activeView === 'transactions' && (
          <div className="animate-stage">
            {/* SCULPTURAL TYPOGRAPHIC HERO & ANALOG LIGHT-METER */}
            <section className="pb-10 border-b border-[#141311]/15">
              <div className="flex flex-col md:flex-row md:items-end justify-between gap-8">
                <div>
                  <div className="flex items-center gap-2.5 text-[11px] font-mono uppercase tracking-[0.18em] text-[#635E54] mb-2">
                    <span>Schedule C Deductible</span>
                    <span>&bull;</span>
                    <span>{analysis.detected_bank_format}</span>
                  </div>
                  <div className="font-serif text-7xl sm:text-8xl leading-[0.9] tracking-tight text-[#141311]">
                    ${analysis.estimated_deductible_total.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                  </div>
                  <p className="text-xs font-mono text-[#635E54] mt-3">
                    Net of −${analysis.total_refund_offsets.toFixed(2)} contra-expense refunds &amp; 50% statutory meals cap
                    {(analysis.provisional_spending || analysis.needs_review_count > 0) && (
                      <span className="text-[#FF4F17] ml-2">
                        &bull; Provisional (${(analysis.amount_in_review || 0).toFixed(2)} in review)
                      </span>
                    )}
                  </p>
                </div>

                {/* Free-standing Typographic Figures */}
                <div className="flex flex-wrap items-end gap-8 md:gap-10">
                  <div>
                    <div className="text-[10px] font-mono uppercase tracking-[0.18em] text-[#635E54]">Net Outflows</div>
                    <div className="font-serif text-4xl leading-none mt-1.5">
                      ${analysis.net_expenses.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                    </div>
                  </div>
                  <div>
                    <div className="text-[10px] font-mono uppercase tracking-[0.18em] text-[#635E54]">Gross Revenue</div>
                    <div className="font-serif text-4xl leading-none text-[#12734C] mt-1.5">
                      +${analysis.gross_income.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                    </div>
                  </div>
                  <div>
                    <div className="text-[10px] font-mono uppercase tracking-[0.18em] text-[#FF4F17]">
                      {analysis.needs_review_count > 0 ? `${analysis.needs_review_count} Unsure` : 'Sorted'}
                    </div>
                    <div className="font-serif text-4xl leading-none mt-1.5">
                      {analysis.auto_categorized_count}/{analysis.total_rows}
                    </div>
                  </div>
                </div>
              </div>

              {/* Analog Camera Light-Meter Exposure Strip */}
              <div className="mt-8 pt-4 border-t border-[#141311]/10 flex items-center gap-3">
                <span className="text-[10px] font-mono uppercase tracking-[0.18em] text-[#635E54] shrink-0">
                  Exposure Index
                </span>
                <div className="flex-1 flex items-center gap-1 h-2.5">
                  {analysis.transactions.map((t) => (
                    <div
                      key={t.id}
                      title={`${t.raw_description}: ${t.category}`}
                      className={`h-full flex-1 rounded-xs transition-all duration-300 ${
                        t.needs_review
                          ? 'bg-[#FF4F17]'
                          : t.transaction_type === 'refund'
                          ? 'bg-[#12734C]'
                          : t.transaction_type === 'transfer' || t.transaction_type === 'excluded'
                          ? 'bg-[#141311]/15'
                          : 'bg-[#141311]/65'
                      }`}
                    />
                  ))}
                </div>
                <span className="text-[10px] font-mono text-[#635E54] shrink-0">
                  {Math.round((analysis.auto_categorized_count / Math.max(1, analysis.total_rows)) * 100)}% Auto
                </span>
              </div>
            </section>

            {/* OPEN-CANVAS FLOATING SPOTLIGHT STAGE FOR NEEDS REVIEW (Zero Card Box!) */}
            {activeReviewTx && (
              <section className="py-10 border-b-2 border-[#141311] animate-stage">
                <div className="flex flex-wrap items-center justify-between gap-4 mb-4">
                  <div className="flex items-center gap-2.5">
                    <span className="w-2.5 h-2.5 rounded-full bg-[#FF4F17] beacon-dot inline-block" />
                    <span className="text-[11px] font-mono uppercase tracking-[0.2em] text-[#FF4F17] font-semibold">
                      Needs Review Spotlight &bull; {(reviewCursor % reviewQueue.length) + 1} of {reviewQueue.length}
                    </span>
                    <span className="text-xs font-mono text-[#635E54]">
                      &bull; {activeReviewTx.date} &bull; Row #{activeReviewTx.row_index}
                    </span>
                  </div>

                  <div className="flex items-center gap-3 text-xs font-mono text-[#635E54]">
                    <button
                      type="button"
                      onClick={() => setReviewCursor((prev) => (prev > 0 ? prev - 1 : reviewQueue.length - 1))}
                      className="hover:text-[#141311] transition cursor-pointer flex items-center gap-0.5"
                    >
                      <ChevronLeft className="w-3.5 h-3.5" /> Prev
                    </button>
                    <span>/</span>
                    <button
                      type="button"
                      onClick={handleSkip}
                      className="hover:text-[#141311] transition cursor-pointer"
                      title="Shortcut: S"
                    >
                      Skip [S]
                    </button>
                    <span>/</span>
                    <button
                      type="button"
                      onClick={() => setReviewCursor((prev) => (prev + 1) % reviewQueue.length)}
                      className="hover:text-[#141311] transition cursor-pointer flex items-center gap-0.5"
                    >
                      Next <ChevronRight className="w-3.5 h-3.5" />
                    </button>
                    {history.length > 0 && (
                      <>
                        <span>/</span>
                        <button
                          type="button"
                          onClick={handleUndo}
                          className="text-[#FF4F17] hover:underline flex items-center gap-1 cursor-pointer"
                          title="Shortcut: U"
                        >
                          <RotateCcw className="w-3 h-3" /> Undo [U]
                        </button>
                      </>
                    )}
                  </div>
                </div>

                <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-8">
                  <div className="space-y-2 max-w-2xl">
                    <div className="flex flex-wrap items-baseline gap-4">
                      <h2 className="font-serif text-5xl sm:text-6xl leading-none tracking-tight text-[#141311]">
                        {friendlyVendorName(activeReviewTx.normalized_merchant, activeReviewTx.raw_description)}
                      </h2>
                      <span className="font-serif text-4xl text-[#FF4F17]">
                        ${activeReviewTx.abs_amount.toFixed(2)}
                      </span>
                    </div>
                    <div className="text-xs font-mono text-[#635E54]">
                      RAW STATEMENT LINE: &ldquo;{activeReviewTx.raw_description}&rdquo;
                    </div>
                    <p className="text-sm text-[#635E54] leading-relaxed pt-1">{activeReviewTx.explanation}</p>
                  </div>

                  {/* Magnetic Pill Actions (No Box Container) */}
                  <div className="space-y-3 lg:text-right">
                    <div className="text-[10px] font-mono uppercase tracking-[0.18em] text-[#635E54]">
                      Assign Schedule C Category (Keys 1–3)
                    </div>
                    <div className="flex flex-wrap lg:justify-end gap-2">
                      {activeReviewTx.suggested_categories.slice(0, 3).map((sug, idx) => (
                        <button
                          key={sug}
                          type="button"
                          onClick={() => handleAssignCategory(activeReviewTx, sug)}
                          className="magnetic-pill px-4 py-2 rounded-full bg-[#141311] hover:bg-[#FF4F17] text-[#F3EFE6] text-xs font-medium flex items-center gap-2 cursor-pointer"
                        >
                          <span>{sug}</span>
                          <span className="text-[10px] font-mono opacity-60">[{idx + 1}]</span>
                        </button>
                      ))}

                      <select
                        onChange={(e) => {
                          if (e.target.value) handleAssignCategory(activeReviewTx, e.target.value);
                        }}
                        value=""
                        className="px-3.5 py-2 rounded-full border border-[#141311]/25 bg-transparent text-xs font-medium text-[#141311] hover:border-[#141311] cursor-pointer focus:outline-none"
                      >
                        <option value="" disabled>
                          More Categories...
                        </option>
                        {ALL_CATEGORIES.filter((c) => c !== 'Needs Review').map((c) => (
                          <option key={c} value={c}>
                            {c}
                          </option>
                        ))}
                      </select>

                      <button
                        type="button"
                        onClick={() => handleExcludeRow(activeReviewTx)}
                        className="px-3 py-2 text-xs font-mono text-[#635E54] hover:text-red-700 transition cursor-pointer"
                      >
                        Exclude Row
                      </button>
                    </div>

                    <label className="inline-flex items-center gap-2 text-xs font-mono text-[#635E54] cursor-pointer">
                      <input
                        type="checkbox"
                        checked={rememberVendor}
                        onChange={(e) => setRememberVendor(e.target.checked)}
                        className="accent-[#FF4F17]"
                      />
                      <span>Remember vendor rule for future rows</span>
                    </label>
                  </div>
                </div>
              </section>
            )}

            {/* ARCHITECTURAL HAIRLINE FILTER STRIP */}
            <section className="pt-8">
              <div className="flex flex-wrap items-center justify-between gap-4 pb-3 border-b-2 border-[#141311]">
                <div className="flex flex-wrap items-center gap-6">
                  {(
                    [
                      ['all', `All Rows (${analysis.total_rows})`],
                      ['needs_review', `Needs Review (${analysis.needs_review_count})`],
                      ['refunds', `Contra-Refunds (${analysis.refund_count})`],
                      ['transfers', `Transfers (${analysis.transfer_count})`],
                      ['section179', `Section 179 ($2.5k+)`],
                    ] as const
                  ).map(([mode, label]) => (
                    <button
                      key={mode}
                      type="button"
                      onClick={() => setFilterMode(mode)}
                      className={`text-xs font-mono uppercase tracking-wider pb-1 transition cursor-pointer ${
                        filterMode === mode
                          ? 'text-[#141311] font-semibold border-b-2 border-[#FF4F17]'
                          : 'text-[#635E54] hover:text-[#141311]'
                      }`}
                    >
                      {label}
                    </button>
                  ))}
                </div>

                <div className="flex items-center gap-4">
                  <select
                    value={categoryFilter}
                    onChange={(e) => setCategoryFilter(e.target.value)}
                    className="bg-transparent text-xs font-mono text-[#635E54] hover:text-[#141311] focus:outline-none cursor-pointer"
                    aria-label="Filter by tax category"
                  >
                    <option value="ALL">All Categories</option>
                    {ALL_CATEGORIES.map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </select>

                  <div className="relative flex items-center border-b border-[#141311]/20 focus-within:border-[#FF4F17]">
                    <Search className="w-3.5 h-3.5 text-[#635E54] mr-1.5" />
                    <input
                      type="text"
                      placeholder="Filter vendor..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      className="bg-transparent py-1 text-xs font-mono w-36 focus:outline-none placeholder:text-[#635E54]/60"
                    />
                  </div>
                </div>
              </div>

              {/* OPEN-CANVAS TRANSACTION STREAM (Hairline rows, spring slide hover) */}
              <div className="divide-y divide-[#141311]/10">
                {filteredTransactions.map((tx, idx) => (
                  <div
                    key={tx.id}
                    onClick={() => setDrawerTxId(tx.id)}
                    style={{ animationDelay: `${Math.min(idx * 18, 240)}ms` }}
                    className="ledger-row py-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 cursor-pointer group"
                  >
                    <div className="flex items-baseline gap-4 min-w-0 flex-1">
                      <span className="font-mono text-xs text-[#635E54] w-24 shrink-0">{tx.date}</span>
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-baseline gap-2.5">
                          <span className="font-serif text-2xl text-[#141311] group-hover:text-[#FF4F17] transition">
                            {friendlyVendorName(tx.normalized_merchant, tx.raw_description)}
                          </span>
                          {tx.needs_review && (
                            <span className="text-[10px] font-mono uppercase tracking-widest text-[#FF4F17] font-semibold">
                              &bull; Needs Review
                            </span>
                          )}
                          {tx.tax_flag === 'SECTION_179_CANDIDATE' && (
                            <span className="text-[10px] font-mono uppercase tracking-wider text-purple-800">
                              &bull; Sec 179 ($2.5k+)
                            </span>
                          )}
                          {tx.tax_flag === 'MEALS_50_PERCENT' && (
                            <span className="text-[10px] font-mono uppercase tracking-wider text-amber-800">
                              &bull; 50% Meal Cap
                            </span>
                          )}
                          {tx.transaction_type === 'refund' && (
                            <span className="text-[10px] font-mono uppercase tracking-wider text-[#12734C]">
                              &bull; Contra-Refund
                            </span>
                          )}
                          {tx.tax_flag === 'INTERNAL_TRANSFER' && (
                            <span className="text-[10px] font-mono uppercase tracking-wider text-[#635E54]">
                              &bull; Excluded Transfer
                            </span>
                          )}
                          {tx.user_overridden && (
                            <span className="text-[10px] font-mono uppercase tracking-wider text-blue-800">
                              &bull; User Rule
                            </span>
                          )}
                        </div>
                        <div className="font-mono text-[11px] text-[#635E54] truncate">{tx.raw_description}</div>
                      </div>
                    </div>

                    <div className="flex items-center justify-between sm:justify-end gap-6 shrink-0" onClick={(e) => e.stopPropagation()}>
                      <select
                        value={tx.category}
                        onChange={(e) => handleAssignCategory(tx, e.target.value)}
                        aria-label={`Tax category for ${tx.raw_description}`}
                        className={`bg-transparent text-xs font-mono py-1 border-b cursor-pointer focus:outline-none transition ${
                          tx.needs_review
                            ? 'border-[#FF4F17] text-[#FF4F17] font-semibold'
                            : 'border-transparent text-[#635E54] hover:text-[#141311] hover:border-[#141311]/30'
                        }`}
                      >
                        {ALL_CATEGORIES.map((cat) => (
                          <option key={cat} value={cat}>
                            {cat}
                          </option>
                        ))}
                      </select>

                      <span
                        onClick={() => setDrawerTxId(tx.id)}
                        className={`font-serif text-2xl w-28 text-right ${
                          tx.amount > 0 ? 'text-[#12734C]' : 'text-[#141311]'
                        }`}
                      >
                        {tx.amount > 0 ? '+' : '−'}${tx.abs_amount.toFixed(2)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          </div>
        )}

        {/* SCHEDULE C PROPORTIONAL HORIZON VIEW (Zero Boxes) */}
        {analysis && activeView === 'categories' && (
          <section className="animate-stage space-y-8">
            <div className="border-b-2 border-[#141311] pb-4 flex flex-wrap items-baseline justify-between gap-4">
              <div>
                <h2 className="font-serif text-5xl">IRS Schedule C Rollup</h2>
                <p className="text-xs font-mono text-[#635E54] mt-1">
                  Line-by-line deductible totals net of contra-expense refunds and statutory meal limits.
                </p>
              </div>
              <div className="text-right">
                <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-[#635E54]">Total Deductible</span>
                <div className="font-serif text-4xl text-[#141311]">
                  ${analysis.estimated_deductible_total.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                </div>
              </div>
            </div>

            <div className="divide-y divide-[#141311]/10">
              {analysis.category_summaries.map((s) => {
                const pct = Math.min(
                  100,
                  Math.round((s.deductible_amount / Math.max(1, analysis.estimated_deductible_total)) * 100)
                );
                return (
                  <div key={s.category} className="py-5 space-y-2">
                    <div className="flex flex-wrap items-baseline justify-between gap-4">
                      <div className="flex flex-wrap items-baseline gap-3">
                        <span className="font-serif text-3xl">{s.category}</span>
                        <span className="font-mono text-xs text-[#635E54]">{s.schedule_c_line}</span>
                      </div>
                      <div className="text-right">
                        <span className="font-serif text-3xl">${s.deductible_amount.toFixed(2)}</span>
                        <span className="font-mono text-xs text-[#635E54] ml-3">
                          ({s.transaction_count} rows &bull; Net ${s.net_spend.toFixed(2)})
                        </span>
                      </div>
                    </div>
                    <div className="w-full h-1 bg-[#141311]/10 overflow-hidden">
                      <div className="h-full bg-[#141311] transition-all duration-500" style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                );
              })}
            </div>

            <p className="pt-4 border-t border-[#141311]/15 text-xs font-mono text-[#635E54]">
              {analysis.tax_disclaimer}
            </p>
          </section>
        )}
      </main>

      {/* FLOATING BOTTOM PILL DOCK */}
      <nav
        className="fixed bottom-6 left-1/2 -translate-x-1/2 z-30 flex items-center gap-1.5 p-1.5 rounded-full bg-[#141311]/95 backdrop-blur-md text-[#F3EFE6] shadow-2xl"
        aria-label="View switcher"
      >
        <button
          type="button"
          onClick={() => setActiveView('transactions')}
          className={`px-4 py-2 rounded-full text-xs font-mono uppercase tracking-wider transition flex items-center gap-1.5 cursor-pointer ${
            activeView === 'transactions' ? 'bg-[#FF4F17] text-white' : 'text-[#F3EFE6]/70 hover:text-white'
          }`}
        >
          <Layers className="w-3.5 h-3.5" />
          <span>Ledger Stream</span>
        </button>
        <button
          type="button"
          onClick={() => setActiveView('categories')}
          className={`px-4 py-2 rounded-full text-xs font-mono uppercase tracking-wider transition flex items-center gap-1.5 cursor-pointer ${
            activeView === 'categories' ? 'bg-[#FF4F17] text-white' : 'text-[#F3EFE6]/70 hover:text-white'
          }`}
        >
          <FileSpreadsheet className="w-3.5 h-3.5" />
          <span>Schedule C Rollup</span>
        </button>
      </nav>

      {/* SLIDE-OVER DECISION INSPECTOR DRAWER (Architectural Hairlines, Zero Nested Card Boxes) */}
      {drawerTx && (
        <div
          className="fixed inset-0 bg-[#141311]/45 backdrop-blur-xs z-40 flex justify-end"
          onClick={() => setDrawerTxId(null)}
        >
          <aside
            className="animate-stage w-full max-w-lg bg-[#F3EFE6] h-full p-8 space-y-6 shadow-2xl overflow-y-auto border-l border-[#141311]/15"
            onClick={(e) => e.stopPropagation()}
            aria-label="Brain Decision Inspector"
          >
            <div className="flex items-start justify-between border-b border-[#141311]/15 pb-4">
              <div>
                <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-[#635E54]">
                  Brain Decision Inspector &bull; Row #{drawerTx.row_index}
                </span>
                <h3 className="font-serif text-4xl text-[#141311] mt-1">
                  {friendlyVendorName(drawerTx.normalized_merchant, drawerTx.raw_description)}
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setDrawerTxId(null)}
                className="p-1.5 rounded-full hover:bg-black/5 text-[#635E54] hover:text-[#141311] cursor-pointer"
                aria-label="Close inspector drawer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Confidence Meter */}
            <div className="space-y-2 pb-5 border-b border-[#141311]/10">
              <div className="flex items-center justify-between text-xs font-mono">
                <span className="text-[#635E54] uppercase tracking-wider">Deterministic Confidence</span>
                <span className="font-semibold text-[#141311]">
                  {(drawerTx.confidence * 100).toFixed(0)}% ({drawerTx.confidence >= 0.7 ? 'Auto-Sorted' : 'Needs Review'})
                </span>
              </div>
              <div className="w-full h-1.5 bg-[#141311]/10 overflow-hidden">
                <div
                  className={`h-full transition-all duration-300 ${
                    drawerTx.confidence >= 0.7 ? 'bg-[#12734C]' : 'bg-[#FF4F17]'
                  }`}
                  style={{ width: `${Math.min(100, drawerTx.confidence * 100)}%` }}
                />
              </div>
            </div>

            {/* Raw & Normalized Identity */}
            <div className="space-y-2 pb-5 border-b border-[#141311]/10 font-mono text-xs">
              <div>
                <span className="text-[#635E54]">RAW BANK LINE: </span>
                <span className="text-[#141311]">&ldquo;{drawerTx.raw_description}&rdquo;</span>
              </div>
              <div>
                <span className="text-[#635E54]">NORMALIZED MERCHANT: </span>
                <span className="text-[#FF4F17]">{drawerTx.normalized_merchant}</span>
              </div>
              <div>
                <span className="text-[#635E54]">SIGNED AMOUNT: </span>
                <span>{drawerTx.amount > 0 ? '+' : '−'}${drawerTx.abs_amount.toFixed(2)}</span>
              </div>
              <div>
                <span className="text-[#635E54]">MATCHED RULE: </span>
                <span>{drawerTx.matched_rule}</span>
              </div>
            </div>

            {/* Tax Rationale */}
            <div className="space-y-2 pb-5 border-b border-[#141311]/10">
              <div className="text-[10px] font-mono uppercase tracking-[0.18em] text-[#635E54]">Decision Trace</div>
              <p className="text-sm text-[#141311] leading-relaxed">{drawerTx.explanation}</p>
              {drawerTx.tax_note && (
                <p className="text-xs font-mono text-[#FF4F17] pt-1">{drawerTx.tax_note}</p>
              )}
            </div>

            {/* Multi-Signal Evidence Weights */}
            {drawerTx.signals && drawerTx.signals.length > 0 && (
              <div className="space-y-2 pb-5 border-b border-[#141311]/10">
                <div className="text-[10px] font-mono uppercase tracking-[0.18em] text-[#635E54]">Evidence Signals</div>
                <div className="divide-y divide-[#141311]/10 font-mono text-xs">
                  {drawerTx.signals.map((sig, idx) => (
                    <div key={idx} className="py-2 flex items-start justify-between gap-3">
                      <div>
                        <div className="text-[#141311]">{sig.layer}: {sig.rule_id}</div>
                        <div className="text-[11px] text-[#635E54] font-sans">{sig.detail}</div>
                      </div>
                      <span className={sig.weight >= 0 ? 'text-[#12734C]' : 'text-[#FF4F17]'}>
                        {sig.weight >= 0 ? `+${sig.weight.toFixed(2)}` : sig.weight.toFixed(2)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Top-2 Alternative Categories ("Why Not") */}
            {drawerTx.alternative_reasons && drawerTx.alternative_reasons.length > 0 && (
              <div className="space-y-2 pb-5 border-b border-[#141311]/10">
                <div className="text-[10px] font-mono uppercase tracking-[0.18em] text-[#635E54]">
                  Alternative Categories Evaluated (&ldquo;Why Not&rdquo;)
                </div>
                <div className="divide-y divide-[#141311]/10">
                  {drawerTx.alternative_reasons.map((alt, idx) => (
                    <div key={idx} className="py-2 space-y-0.5">
                      <div className="text-xs font-mono font-semibold text-[#141311]">{alt.category}</div>
                      <div className="text-xs text-[#635E54]">{alt.reason}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Override Classification */}
            <div className="space-y-3">
              <div className="text-[10px] font-mono uppercase tracking-[0.18em] text-[#635E54]">
                Override Classification
              </div>
              <select
                value={drawerTx.category}
                onChange={(e) => handleAssignCategory(drawerTx, e.target.value)}
                className="w-full py-2 border-b-2 border-[#141311] bg-transparent text-sm font-mono text-[#141311] focus:outline-none cursor-pointer"
              >
                {ALL_CATEGORIES.map((cat) => (
                  <option key={cat} value={cat}>
                    {cat}
                  </option>
                ))}
              </select>
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}
