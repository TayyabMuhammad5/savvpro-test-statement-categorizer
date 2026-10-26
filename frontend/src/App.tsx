import React, { useEffect, useMemo, useState } from 'react';
import { analyzeStatement, fetchPresets } from './api';
import {
  CategorizedTransaction,
  SamplePreset,
  StatementAnalysisResponse,
} from './types';

const ALL_CATEGORIES = [
  'Gear & Lens Rentals',
  'Camera Equipment & Lighting',
  'Photobook Printing & Lab COGS',
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
    .replace(/\bIsbn\b/g, 'ISBN');
}

export default function App() {
  const [presets, setPresets] = useState<SamplePreset[]>([]);
  const [selectedPresetId, setSelectedPresetId] = useState<string>('chase_studio_card');
  const [statementName, setStatementName] = useState<string>('chase_studio_credit_card_2025.csv');
  const [csvContent, setCsvContent] = useState<string>('');
  const [customRules, setCustomRules] = useState<Record<string, string>>({});
  const [analysis, setAnalysis] = useState<StatementAnalysisResponse | null>(null);
  const [activeView, setActiveView] = useState<'transactions' | 'categories'>('transactions');
  const [filterMode, setFilterMode] = useState<'all' | 'needs_review' | 'refunds' | 'transfers'>('all');
  const [categoryFilter, setCategoryFilter] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [drawerTxId, setDrawerTxId] = useState<string | null>(null);
  const [reviewCursor, setReviewCursor] = useState<number>(0);
  const [rememberVendor, setRememberVendor] = useState<boolean>(true);
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
    analyzeStatement(statementName, csvContent, customRules)
      .then((res) => setAnalysis(res))
      .catch((err) => setError(err.message));
  }, [csvContent, statementName, customRules]);

  const handlePresetChange = (presetId: string) => {
    const found = presets.find((p) => p.id === presetId);
    if (!found) return;
    setSelectedPresetId(found.id);
    setStatementName(found.filename);
    setCsvContent(found.csv);
    setReviewCursor(0);
    setDrawerTxId(null);
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      const text = String(ev.target?.result || '');
      setStatementName(file.name);
      setCsvContent(text);
      setSelectedPresetId('custom');
      setReviewCursor(0);
      setDrawerTxId(null);
    };
    reader.readAsText(file);
  };

  const handleAssignCategory = (tx: CategorizedTransaction, newCategory: string) => {
    const key = rememberVendor ? tx.normalized_merchant : tx.raw_description;
    setCustomRules((prev) => ({
      ...prev,
      [key]: newCategory,
    }));
  };

  const filteredTransactions = useMemo(() => {
    if (!analysis) return [];
    return analysis.transactions.filter((tx) => {
      if (filterMode === 'needs_review' && !tx.needs_review) return false;
      if (filterMode === 'refunds' && tx.transaction_type !== 'refund') return false;
      if (filterMode === 'transfers' && tx.transaction_type !== 'transfer' && tx.transaction_type !== 'duplicate') return false;
      if (categoryFilter !== 'ALL' && tx.category !== categoryFilter) return false;
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        return (
          tx.raw_description.toLowerCase().includes(q) ||
          tx.normalized_merchant.toLowerCase().includes(q) ||
          tx.category.toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [analysis, filterMode, categoryFilter, searchQuery]);

  const reviewQueue = useMemo(() => {
    if (!analysis) return [];
    return analysis.transactions.filter((t) => t.needs_review);
  }, [analysis]);

  const activeReviewTx = reviewQueue.length > 0 ? reviewQueue[reviewCursor % reviewQueue.length] : null;

  const drawerTx = useMemo(() => {
    if (!analysis || !drawerTxId) return null;
    return analysis.transactions.find((t) => t.id === drawerTxId) || null;
  }, [analysis, drawerTxId]);

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
      'Confidence',
      'Needs_Review',
      'Deductible_Rate',
      'Net_Deductible_Impact',
      'Tax_Flag',
      'Matched_Rule',
    ];
    const rows = analysis.transactions.map((t) => [
      t.row_index,
      t.date,
      `"${t.raw_description.replace(/"/g, '""')}"`,
      `"${t.normalized_merchant.replace(/"/g, '""')}"`,
      t.amount.toFixed(2),
      t.transaction_type,
      `"${t.category}"`,
      t.confidence.toFixed(2),
      t.needs_review,
      t.deductible_rate,
      t.deductible_impact.toFixed(2),
      t.tax_flag,
      t.matched_rule,
    ]);
    const csvBlob = [headers.join(','), ...rows.map((r) => r.join(','))].join('\n');
    const blob = new Blob([csvBlob], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `categorized_${statementName}`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="min-h-screen bg-[#F3EFE6] text-[#141311] pb-28">
      {/* Open, Un-Boxed Minimal Header */}
      <header className="max-w-5xl mx-auto px-6 pt-7 pb-4 flex flex-wrap items-center justify-between gap-4 border-b border-[#141311]/10">
        <div className="flex flex-wrap items-center gap-5">
          <div className="flex items-center gap-2.5">
            <span className="w-3 h-3 rounded-full bg-[#FF4F17] inline-block" />
            <span className="font-serif text-2xl tracking-tight">Focal &amp; Folio</span>
          </div>
          <span className="text-[#141311]/20">/</span>
          <div className="flex flex-wrap items-center gap-4 text-xs">
            {presets.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => handlePresetChange(p.id)}
                className={
                  selectedPresetId === p.id
                    ? 'font-semibold text-[#141311] underline decoration-[#FF4F17] decoration-2 underline-offset-4'
                    : 'text-[#635E54] hover:text-[#141311]'
                }
              >
                {p.name}
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-5 text-xs font-medium">
          <label className="cursor-pointer text-[#635E54] hover:text-[#141311] transition">
            <span>+ Import CSV</span>
            <input type="file" accept=".csv" className="hidden" onChange={handleFileUpload} />
          </label>
          <button
            type="button"
            onClick={exportScheduleCCsv}
            className="px-4 py-1.5 rounded-full bg-[#141311] hover:bg-[#FF4F17] text-[#F3EFE6] text-xs font-medium transition"
          >
            Export Sorted CSV &nearr;
          </button>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 pt-10 space-y-12">
        {error && <div className="text-xs text-[#FF4F17] font-mono">{error}</div>}

        {analysis && activeView === 'transactions' && (
          <>
            {/* Open Sculptural Typographic Hero (No Box!) */}
            <section className="grid grid-cols-1 md:grid-cols-12 gap-8 items-end pb-8 border-b border-[#141311]/10">
              <div className="md:col-span-6 space-y-1">
                <div className="text-[11px] font-mono uppercase tracking-widest text-[#635E54]">
                  Schedule C Deductible &bull; {analysis.detected_bank_format}
                </div>
                <div className="font-serif text-6xl sm:text-7xl leading-none tracking-tight">
                  ${analysis.estimated_deductible_total.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                </div>
                <p className="text-xs text-[#635E54] pt-1">
                  Net of ${analysis.total_refund_offsets.toFixed(2)} vendor refunds &amp; 50% meal cap
                </p>
              </div>

              <div className="md:col-span-6 flex flex-wrap items-end justify-between gap-6">
                <div>
                  <div className="text-[11px] font-mono uppercase tracking-widest text-[#635E54]">Net Spend</div>
                  <div className="font-serif text-4xl leading-none mt-1">
                    ${analysis.net_expenses.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                  </div>
                </div>
                <div>
                  <div className="text-[11px] font-mono uppercase tracking-widest text-[#635E54]">Gross Revenue</div>
                  <div className="font-serif text-4xl leading-none text-[#12734C] mt-1">
                    ${analysis.gross_income.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                  </div>
                </div>
                <div>
                  <div className="text-[11px] font-mono uppercase tracking-widest text-[#FF4F17]">
                    {analysis.needs_review_count} Unsure
                  </div>
                  <div className="font-serif text-4xl leading-none mt-1">
                    {analysis.auto_categorized_count}/{analysis.total_rows}
                  </div>
                </div>
              </div>
            </section>

            {/* Open Kinetic Review Stage (No Box!) */}
            {activeReviewTx && (
              <section className="pb-10 border-b border-[#141311]/10 grid grid-cols-1 lg:grid-cols-12 gap-6 items-center">
                <div className="lg:col-span-7 space-y-2">
                  <div className="text-[11px] font-mono uppercase tracking-widest text-[#FF4F17] font-semibold">
                    Unsure Item {(reviewCursor % reviewQueue.length) + 1} of {reviewQueue.length} &bull; {activeReviewTx.date}
                  </div>
                  <div className="flex items-baseline gap-4">
                    <h3 className="font-serif text-4xl sm:text-5xl leading-none">
                      {friendlyVendorName(activeReviewTx.normalized_merchant, activeReviewTx.raw_description)}
                    </h3>
                    <span className="font-mono text-2xl text-[#FF4F17]">
                      ${activeReviewTx.abs_amount.toFixed(2)}
                    </span>
                  </div>
                  <p className="text-sm text-[#635E54]">{activeReviewTx.explanation}</p>
                </div>

                <div className="lg:col-span-5 flex flex-wrap lg:justify-end gap-2">
                  {activeReviewTx.suggested_categories.slice(0, 3).map((sug) => (
                    <button
                      key={sug}
                      type="button"
                      onClick={() => handleAssignCategory(activeReviewTx, sug)}
                      className="px-4 py-2 rounded-full border border-[#141311] hover:bg-[#141311] hover:text-[#F3EFE6] text-xs font-medium transition"
                    >
                      {sug}
                    </button>
                  ))}
                </div>
              </section>
            )}

            {/* Borderless Open-Canvas Transaction Stream */}
            <section className="space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-4 pb-3 border-b-2 border-[#141311]">
                <div className="flex flex-wrap gap-6">
                  {(
                    [
                      ['all', `All (${analysis.total_rows})`],
                      ['needs_review', `Needs Review (${analysis.needs_review_count})`],
                      ['refunds', `Refunds (${analysis.refund_count})`],
                      ['transfers', `Transfers (${analysis.transfer_count})`],
                    ] as const
                  ).map(([mode, label]) => (
                    <button
                      key={mode}
                      type="button"
                      onClick={() => setFilterMode(mode)}
                      className={
                        filterMode === mode
                          ? 'text-xs font-semibold text-[#141311] border-b-2 border-[#FF4F17] pb-1'
                          : 'text-xs font-medium text-[#635E54] hover:text-[#141311] pb-1'
                      }
                    >
                      {label}
                    </button>
                  ))}
                </div>

                <div className="flex items-center gap-4">
                  <select
                    value={categoryFilter}
                    onChange={(e) => setCategoryFilter(e.target.value)}
                    className="bg-transparent text-xs text-[#635E54] focus:outline-none"
                  >
                    <option value="ALL">All Categories</option>
                    {ALL_CATEGORIES.map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </select>
                  <input
                    type="text"
                    placeholder="Search vendor..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="bg-transparent border-b border-[#141311]/25 px-1 py-0.5 text-xs w-40 focus:outline-none focus:border-[#FF4F17]"
                  />
                </div>
              </div>

              <table className="w-full text-left border-collapse">
                <tbody className="divide-y divide-[#141311]/10 text-sm">
                  {filteredTransactions.map((tx) => (
                    <tr
                      key={tx.id}
                      onClick={() => setDrawerTxId(tx.id)}
                      className="hover:translate-x-1.5 transition-transform cursor-pointer"
                    >
                      <td className="py-4 pr-4 font-mono text-xs text-[#635E54] whitespace-nowrap">{tx.date}</td>
                      <td className="py-4 px-2 font-medium text-base">
                        {friendlyVendorName(tx.normalized_merchant, tx.raw_description)}
                      </td>
                      <td className="py-4 px-3 w-64" onClick={(e) => e.stopPropagation()}>
                        <select
                          value={tx.category}
                          onChange={(e) => handleAssignCategory(tx, e.target.value)}
                          className={`w-full bg-transparent text-xs py-1 border-b ${
                            tx.needs_review ? 'border-[#FF4F17] text-[#FF4F17] font-semibold' : 'border-transparent text-[#635E54]'
                          }`}
                        >
                          {ALL_CATEGORIES.map((cat) => (
                            <option key={cat} value={cat}>
                              {cat}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td className={`py-4 pl-3 text-right font-mono text-sm font-medium ${tx.amount > 0 ? 'text-[#12734C]' : 'text-[#141311]'}`}>
                        {tx.amount > 0 ? '+' : '−'}${tx.abs_amount.toFixed(2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          </>
        )}

        {analysis && activeView === 'categories' && (
          <section className="space-y-8">
            <h2 className="font-serif text-5xl border-b-2 border-[#141311] pb-4">Schedule C Tax Rollup</h2>
            <div className="divide-y divide-[#141311]/10">
              {analysis.category_summaries.map((s) => (
                <div key={s.category} className="py-5 flex items-baseline justify-between">
                  <div>
                    <span className="font-serif text-3xl">{s.category}</span>
                    <span className="font-mono text-xs text-[#635E54] ml-3">{s.schedule_c_line}</span>
                  </div>
                  <span className="font-serif text-3xl">${s.net_spend.toFixed(2)}</span>
                </div>
              ))}
            </div>
          </section>
        )}
      </main>

      {/* Floating Bottom Pill Dock */}
      <nav className="fixed bottom-6 left-1/2 -translate-x-1/2 z-30 flex items-center gap-1 p-1.5 rounded-full bg-[#141311]/90 backdrop-blur-md text-[#F3EFE6] shadow-2xl">
        <button
          type="button"
          onClick={() => setActiveView('transactions')}
          className={`px-4 py-2 rounded-full text-xs font-medium transition ${
            activeView === 'transactions' ? 'bg-[#FF4F17] text-white' : 'text-[#F3EFE6]/70'
          }`}
        >
          Statement Categorizer
        </button>
        <button
          type="button"
          onClick={() => setActiveView('categories')}
          className={`px-4 py-2 rounded-full text-xs font-medium transition ${
            activeView === 'categories' ? 'bg-[#FF4F17] text-white' : 'text-[#F3EFE6]/70'
          }`}
        >
          Category Totals
        </button>
      </nav>

      {/* Slide-Over Detail Drawer */}
      {drawerTx && (
        <div className="fixed inset-0 bg-[#141311]/30 z-40 flex justify-end" onClick={() => setDrawerTxId(null)}>
          <aside
            className="w-full max-w-md bg-[#F3EFE6] h-full p-7 space-y-5 shadow-2xl overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-[#141311]/15 pb-4">
              <h3 className="font-serif text-3xl">Decision Breakdown</h3>
              <button type="button" onClick={() => setDrawerTxId(null)} className="text-lg">
                &times;
              </button>
            </div>
            <div className="font-mono text-sm">{drawerTx.raw_description}</div>
            <p className="text-sm text-[#635E54]">{drawerTx.explanation}</p>
            <label className="inline-flex items-center gap-2 text-xs text-[#635E54]">
              <input
                type="checkbox"
                checked={rememberVendor}
                onChange={(e) => setRememberVendor(e.target.checked)}
              />
              <span>Remember this merchant</span>
            </label>
          </aside>
        </div>
      )}
    </div>
  );
}
