'use client';

import React, { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import {
  Menu, Database, Bot, Table, Sparkles, Paperclip, ArrowUp,
  BarChart2, AlertTriangle, CheckCircle2, CloudUpload,
  MessageSquare, Lightbulb, TrendingUp, ShoppingCart,
  Users, Wrench, Brain,
} from 'lucide-react';

// ---------------------------------------------------------------------------
// Constants & Config
// ---------------------------------------------------------------------------

const API_BASE_URL =
  process.env.NEXT_PUBLIC_DATAVERSE_API_URL?.replace(/\/$/, '') || 'http://127.0.0.1:8000';

// ---------------------------------------------------------------------------
// Type Definitions
// ---------------------------------------------------------------------------

type ChatMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  tables?: Array<{ title: string; columns: string[]; rows: Record<string, unknown>[] }>;
  charts?: Array<{ title: string; type: string; x_key: string; y_key: string; data: Record<string, unknown>[] }>;
  recommendations?: string[];
  warnings?: string[];
  next_questions?: string[];
  isLoading?: boolean;
};

type DatasetInfo = {
  dataset_id: string;
  filename: string;
  row_count: number;
  column_count: number;
  columns: string[];
  profile: Record<string, unknown>;
};

// ---------------------------------------------------------------------------
// Utility Helpers
// ---------------------------------------------------------------------------

const formatNumber = (value?: number): string => {
  if (typeof value !== 'number') return '0';
  return new Intl.NumberFormat('en-US', {
    notation: value > 9999 ? 'compact' : 'standard',
  }).format(value);
};

const formatCell = (value: unknown): string => {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'number') {
    return new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 }).format(value);
  }
  return String(value);
};

// ---------------------------------------------------------------------------
// EXAMPLE PROMPTS
// ---------------------------------------------------------------------------

const EXAMPLE_PROMPTS = [
  { label: 'Highest selling product', icon: ShoppingCart },
  { label: 'Monthly revenue trend', icon: TrendingUp },
  { label: 'Predict next month sales', icon: Brain },
  { label: 'Top customers', icon: Users },
  { label: 'Clean data issues', icon: Wrench },
  { label: 'Business recommendations', icon: Lightbulb },
];

// ---------------------------------------------------------------------------
// GlassCard Component
// ---------------------------------------------------------------------------

const GlassCard = ({
  children,
  className = '',
  onClick,
}: {
  children: React.ReactNode;
  className?: string;
  onClick?: () => void;
}) => (
  <div
    onClick={onClick}
    className={`bg-[#171f33]/60 backdrop-blur-xl border border-[#494454]/30 rounded-xl overflow-hidden ${
      onClick
        ? 'cursor-pointer hover:border-violet-500/50 hover:shadow-[0_0_20px_rgba(139,92,246,0.15)] transition-all duration-300'
        : ''
    } ${className}`}
  >
    {children}
  </div>
);

// ---------------------------------------------------------------------------
// FloatingInput Component
// ---------------------------------------------------------------------------

const FloatingInput = ({
  onSubmit,
  onFileUpload,
  disabled = false,
  placeholder = 'Message DataVerse AI...',
}: {
  onSubmit: (text: string) => void;
  onFileUpload?: (file: File) => void;
  disabled?: boolean;
  placeholder?: string;
}) => {
  const [text, setText] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const submit = () => {
    if (disabled || !text.trim()) return;
    onSubmit(text.trim());
    setText('');
  };

  // Auto-resize textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [text]);

  return (
    <div className="absolute bottom-6 md:bottom-8 left-0 w-full px-4 md:px-8 z-30 pointer-events-none">
      <div className="max-w-[800px] mx-auto relative pointer-events-auto group">
        {/* Glow backdrop */}
        <div className="absolute inset-0 bg-gradient-to-r from-violet-500/10 to-blue-500/10 blur-2xl rounded-full translate-y-2 group-focus-within:from-violet-500/20 group-focus-within:to-blue-500/20 transition-all duration-500" />

        <div className="relative bg-[#2d3449]/90 backdrop-blur-2xl border border-[#494454]/60 rounded-[2rem] p-2 xl:p-2.5 shadow-2xl flex items-end gap-2 focus-within:border-violet-400/60 focus-within:bg-[#2d3449] transition-all">
          {/* File upload button */}
          <label
            className={`p-3 text-[#cbc3d7] hover:text-white transition-colors hover:bg-white/5 rounded-full shrink-0 ${
              onFileUpload ? 'cursor-pointer' : 'opacity-50 cursor-not-allowed'
            }`}
            title="Upload CSV or Excel"
          >
            <input
              type="file"
              accept=".csv,.xlsx,.xls"
              className="hidden"
              disabled={!onFileUpload || disabled}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file && onFileUpload) onFileUpload(file);
                e.target.value = '';
              }}
            />
            <Paperclip size={20} />
          </label>

          {/* Textarea */}
          <div className="flex-1 py-1">
            <textarea
              ref={textareaRef}
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  submit();
                }
              }}
              disabled={disabled}
              className="w-full bg-transparent border-none focus:ring-0 text-white font-sans text-sm placeholder:text-[#cbc3d7]/50 resize-none py-2 px-1 outline-none"
              placeholder={placeholder}
              rows={1}
            />
          </div>

          {/* Send button */}
          <button
            onClick={submit}
            disabled={disabled || !text.trim()}
            className="p-3 bg-gradient-to-br from-violet-400 to-blue-400 text-[#0b1326] rounded-full shrink-0 flex items-center justify-center hover:brightness-110 active:scale-95 transition-all shadow-sm disabled:opacity-50 disabled:grayscale"
          >
            <ArrowUp size={20} />
          </button>
        </div>

        <div className="text-center mt-2">
          <span className="text-[10px] text-[#cbc3d7]/60">
            DataVerse AI can make mistakes. Verify important data.
          </span>
        </div>
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// ResultTable Component
// ---------------------------------------------------------------------------

const ResultTable = ({
  table,
}: {
  table: { title: string; columns: string[]; rows: Record<string, unknown>[] };
}) => (
  <GlassCard className="overflow-hidden border-slate-500/20">
    <div className="flex items-center gap-3 px-4 py-3 border-b border-[#494454]/40 bg-[#0b1326]/40">
      <Table size={16} className="text-violet-300" />
      <span className="text-sm font-medium text-white">{table.title}</span>
      <span className="ml-auto text-[10px] text-[#cbc3d7]/60">
        {table.rows.length} row{table.rows.length !== 1 ? 's' : ''}
      </span>
    </div>
    <div className="overflow-x-auto">
      <table className="w-full text-left text-xs">
        <thead className="bg-[#131b2e] text-[#cbc3d7]">
          <tr>
            {table.columns.map((col) => (
              <th key={col} className="px-4 py-3 font-semibold whitespace-nowrap">
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.slice(0, 10).map((row, idx) => (
            <tr key={idx} className="border-t border-[#494454]/30 text-slate-100">
              {table.columns.map((col) => (
                <td key={col} className="px-4 py-3 whitespace-nowrap">
                  {formatCell(row[col])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  </GlassCard>
);

// ---------------------------------------------------------------------------
// SimpleChart Component
// ---------------------------------------------------------------------------

const SimpleChart = ({
  chart,
}: {
  chart: { title: string; type: string; x_key: string; y_key: string; data: Record<string, unknown>[] };
}) => {
  const values = chart.data.map((row) => Number(row[chart.y_key]) || 0);
  const max = Math.max(...values.map((v) => Math.abs(v)), 1);

  // ---- Line chart ----
  if (chart.type === 'line') {
    const svgW = 520;
    const svgH = 180;
    const points = values
      .map((v, i) => {
        const x = values.length === 1 ? svgW / 2 : (i / (values.length - 1)) * svgW;
        const y = svgH - ((v / max) * (svgH - 20) + 10);
        return `${x},${Math.max(8, Math.min(svgH - 8, y))}`;
      })
      .join(' ');

    return (
      <GlassCard className="p-4 border-blue-500/20">
        <div className="flex items-center gap-3 mb-4">
          <BarChart2 size={16} className="text-blue-400" />
          <span className="text-sm font-medium text-white">{chart.title}</span>
        </div>
        <svg viewBox={`0 0 ${svgW} ${svgH}`} className="w-full h-48 overflow-visible">
          <polyline fill="none" stroke="#60a5fa" strokeWidth="3" points={points} />
          {values.map((_, i) => {
            const [cx, cy] = points.split(' ')[i].split(',').map(Number);
            return <circle key={i} cx={cx} cy={cy} r="4" fill="#a78bfa" />;
          })}
        </svg>
        <div className="flex justify-between gap-3 text-[10px] text-[#cbc3d7] mt-2">
          {chart.data.slice(0, 8).map((row, i) => (
            <span key={i} className="truncate">
              {formatCell(row[chart.x_key])}
            </span>
          ))}
        </div>
      </GlassCard>
    );
  }

  // ---- Bar chart (default / horizontal bars) ----
  return (
    <GlassCard className="p-4 border-blue-500/20">
      <div className="flex items-center gap-3 mb-4">
        <BarChart2 size={16} className="text-blue-400" />
        <span className="text-sm font-medium text-white">{chart.title}</span>
      </div>
      <div className="space-y-3">
        {chart.data.slice(0, 10).map((row, i) => {
          const raw = Number(row[chart.y_key]) || 0;
          const pct = `${Math.max(4, Math.min(100, (Math.abs(raw) / max) * 100))}%`;
          return (
            <div key={i} className="grid grid-cols-[minmax(96px,180px)_1fr_72px] items-center gap-3">
              <span className="text-xs text-[#cbc3d7] truncate">
                {formatCell(row[chart.x_key])}
              </span>
              <div className="h-2.5 rounded-full bg-[#222a3d] overflow-hidden">
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: pct }}
                  transition={{ duration: 0.6, delay: i * 0.05 }}
                  className={`h-full rounded-full ${raw < 0 ? 'bg-rose-400' : 'bg-blue-400'}`}
                />
              </div>
              <span className="text-xs font-mono text-white text-right">{formatCell(raw)}</span>
            </div>
          );
        })}
      </div>
    </GlassCard>
  );
};

// ---------------------------------------------------------------------------
// Sidebar Component
// ---------------------------------------------------------------------------

const Sidebar = ({
  dataset,
  currentView,
  onViewChange,
}: {
  dataset: DatasetInfo | null;
  currentView: 'home' | 'chat';
  onViewChange: (v: 'home' | 'chat') => void;
}) => (
  <aside className="hidden md:flex bg-[#171f33] w-[280px] h-full rounded-r-2xl border-r border-[#494454]/30 shadow-2xl flex-col py-6 shrink-0 z-40">
    {/* Brand */}
    <div className="px-6 mb-8 mt-2">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-500 to-blue-500 flex items-center justify-center shadow-lg">
          <Sparkles size={18} className="text-white" />
        </div>
        <div>
          <h1 className="text-lg font-bold bg-clip-text text-transparent bg-gradient-to-r from-violet-400 to-blue-400 leading-tight">
            DataVerse AI
          </h1>
          <span className="text-[10px] text-[#cbc3d7]/70 font-medium">Analytics Platform</span>
        </div>
      </div>
    </div>

    {/* Navigation */}
    <nav className="flex-1 overflow-y-auto space-y-6 px-3 pb-4">
      <div className="space-y-1">
        <button
          onClick={() => onViewChange('home')}
          className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-xl transition-all duration-200 ${
            currentView === 'home'
              ? 'bg-violet-500/15 text-violet-300 font-medium'
              : 'text-[#cbc3d7] hover:bg-white/5 hover:text-white'
          }`}
        >
          <Sparkles size={18} />
          <span className="text-sm">New Analysis</span>
        </button>
        <button
          onClick={() => onViewChange('chat')}
          className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-xl transition-all duration-200 ${
            currentView === 'chat'
              ? 'bg-violet-500/15 text-violet-300 font-medium'
              : 'text-[#cbc3d7] hover:bg-white/5 hover:text-white'
          }`}
        >
          <MessageSquare size={18} />
          <span className="text-sm">Chat</span>
        </button>
      </div>

      {/* Dataset Info */}
      <div>
        <h3 className="px-4 text-[11px] font-semibold text-[#cbc3d7] uppercase tracking-wider mb-2">
          Active Dataset
        </h3>
        <div className="space-y-1">
          {dataset ? (
            <>
              <div className="flex items-center gap-3 px-4 py-2 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-sm">
                <Database size={16} className="text-emerald-400 shrink-0" />
                <div className="min-w-0">
                  <p className="text-emerald-200 font-medium truncate text-xs">{dataset.filename}</p>
                  <p className="text-[10px] text-emerald-300/60 mt-0.5">
                    {formatNumber(dataset.row_count)} rows · {formatNumber(dataset.column_count)} cols
                  </p>
                </div>
              </div>
              <div className="px-4 py-2">
                <p className="text-[10px] text-[#cbc3d7]/50 uppercase tracking-wider font-semibold mb-1.5">
                  Columns
                </p>
                <div className="flex flex-wrap gap-1">
                  {dataset.columns.slice(0, 8).map((col) => (
                    <span
                      key={col}
                      className="text-[10px] text-[#cbc3d7] bg-[#2d3449] px-2 py-0.5 rounded-full truncate max-w-[120px]"
                    >
                      {col}
                    </span>
                  ))}
                  {dataset.columns.length > 8 && (
                    <span className="text-[10px] text-violet-300 bg-violet-500/10 px-2 py-0.5 rounded-full">
                      +{dataset.columns.length - 8}
                    </span>
                  )}
                </div>
              </div>
            </>
          ) : (
            <div className="flex items-center gap-3 px-4 py-2 text-[#cbc3d7]/50 text-sm">
              <CloudUpload size={16} className="shrink-0" />
              <span className="text-xs">No dataset loaded</span>
            </div>
          )}
        </div>
      </div>
    </nav>

    {/* Footer */}
    <div className="px-4 mt-auto border-t border-[#494454]/30 pt-4">
      <div className="flex items-center gap-2.5 px-4 py-2 text-xs text-[#cbc3d7]/60">
        <span className="relative flex h-2 w-2">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
          <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
        </span>
        <span>Backend: {API_BASE_URL.replace(/^https?:\/\//, '')}</span>
      </div>
    </div>
  </aside>
);

// ---------------------------------------------------------------------------
// MobileNav Component
// ---------------------------------------------------------------------------

const MobileNav = ({
  currentView,
  onViewChange,
}: {
  currentView: 'home' | 'chat';
  onViewChange: (v: 'home' | 'chat') => void;
}) => (
  <nav className="md:hidden fixed bottom-0 left-0 w-full z-50 bg-[#171f33]/90 backdrop-blur-2xl border-t border-[#494454]/40 flex items-center justify-around px-4 py-2 safe-bottom">
    <button
      onClick={() => onViewChange('home')}
      className={`flex flex-col items-center gap-1 py-2 px-4 rounded-xl transition-all ${
        currentView === 'home' ? 'text-violet-400' : 'text-[#cbc3d7]/60'
      }`}
    >
      <Sparkles size={20} />
      <span className="text-[10px] font-medium">Home</span>
    </button>
    <button
      onClick={() => onViewChange('chat')}
      className={`flex flex-col items-center gap-1 py-2 px-4 rounded-xl transition-all ${
        currentView === 'chat' ? 'text-violet-400' : 'text-[#cbc3d7]/60'
      }`}
    >
      <MessageSquare size={20} />
      <span className="text-[10px] font-medium">Chat</span>
    </button>
  </nav>
);

// ---------------------------------------------------------------------------
// HomeView — Main starting view
// ---------------------------------------------------------------------------

const HomeView = ({
  dataset,
  uploadStatus,
  onUpload,
  onSubmit,
}: {
  dataset: DatasetInfo | null;
  uploadStatus: string | null;
  onUpload: (file: File) => void;
  onSubmit: (query: string) => void;
}) => (
  <div className="flex-1 w-full h-full flex flex-col relative overflow-hidden items-center justify-center">
    {/* Background orbs */}
    <div className="absolute top-1/4 left-1/4 w-[500px] h-[500px] bg-violet-600/15 rounded-full blur-[120px] pointer-events-none" />
    <div className="absolute bottom-1/4 right-1/4 w-[500px] h-[500px] bg-blue-600/15 rounded-full blur-[120px] pointer-events-none" />

    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
      className="w-full max-w-[800px] px-4 md:px-8 text-center z-10 flex flex-col items-center -mt-24"
    >
      {/* Heading */}
      <div className="mb-10">
        <h2 className="text-3xl md:text-5xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-white to-[#cbc3d7] tracking-tight mb-4">
          What shall we analyze today?
        </h2>
        <p className="text-sm md:text-base text-[#cbc3d7]/70 max-w-lg mx-auto">
          Upload a CSV or Excel file, then ask natural-language questions to get instant insights, charts, and recommendations.
        </p>
      </div>

      {/* Dataset status card */}
      <GlassCard className="w-full p-4 md:p-5 text-left border-[#494454]/50 mb-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="w-10 h-10 rounded-lg bg-[#2d3449] flex items-center justify-center border border-[#494454]/50 text-violet-400 shrink-0">
              {dataset ? <Table size={20} /> : <CloudUpload size={20} />}
            </div>
            <div>
              <h3 className="text-sm font-semibold text-white">
                {dataset?.filename || 'Upload a CSV or Excel file'}
              </h3>
              <p className="text-xs text-[#cbc3d7] mt-1">
                {uploadStatus ||
                  (dataset
                    ? `${formatNumber(dataset.row_count)} rows · ${formatNumber(dataset.column_count)} columns`
                    : `Backend: ${API_BASE_URL}`)}
              </p>
            </div>
          </div>
          {dataset && (
            <span className="px-3 py-1 bg-emerald-500/10 border border-emerald-500/30 rounded text-xs text-emerald-300 flex items-center gap-2 font-medium self-start md:self-auto">
              <CheckCircle2 size={14} /> Ready
            </span>
          )}
        </div>
      </GlassCard>

      {/* Example prompts — shown only when dataset is loaded */}
      {dataset && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2, duration: 0.4 }}
          className="grid grid-cols-2 md:grid-cols-3 gap-2.5 w-full"
        >
          {EXAMPLE_PROMPTS.map((ep) => (
            <GlassCard
              key={ep.label}
              onClick={() => onSubmit(ep.label)}
              className="p-3 flex items-center gap-2.5 text-left"
            >
              <ep.icon size={16} className="text-violet-400 shrink-0" />
              <span className="text-xs text-[#cbc3d7] leading-tight">{ep.label}</span>
            </GlassCard>
          ))}
        </motion.div>
      )}
    </motion.div>

    {/* Floating input bar */}
    <FloatingInput
      onSubmit={onSubmit}
      onFileUpload={onUpload}
      disabled={uploadStatus?.toLowerCase().includes('uploading') ?? false}
      placeholder={dataset ? 'Ask about your dataset...' : 'Attach a dataset, then ask a question...'}
    />
  </div>
);

// ---------------------------------------------------------------------------
// ChatView — Conversation + results
// ---------------------------------------------------------------------------

const ChatView = ({
  dataset,
  messages,
  isQuerying,
  onUpload,
  onSubmit,
}: {
  dataset: DatasetInfo | null;
  messages: ChatMessage[];
  isQuerying: boolean;
  onUpload: (file: File) => void;
  onSubmit: (query: string) => void;
}) => {
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);

  return (
    <div className="flex-1 w-full h-full flex flex-col relative overflow-hidden">
      {/* Scrollable messages area */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto w-full px-4 md:px-8 scroll-smooth">
        <div className="max-w-[800px] mx-auto pt-6 flex flex-col pb-48 space-y-6">
          {/* Dataset missing warning */}
          {!dataset && (
            <GlassCard className="p-5 border-amber-500/20">
              <div className="flex items-start gap-3">
                <AlertTriangle className="text-amber-400 shrink-0 mt-0.5" size={18} />
                <div>
                  <h3 className="text-sm font-semibold text-white">Dataset needed</h3>
                  <p className="text-sm text-[#cbc3d7] mt-1">
                    Use the paperclip button to upload a CSV or Excel file before asking questions.
                  </p>
                </div>
              </div>
            </GlassCard>
          )}

          {/* Active dataset badge */}
          {dataset && (
            <GlassCard className="p-3 border-[#494454]/50">
              <div className="flex items-center justify-between gap-4">
                <div className="flex items-center gap-3 min-w-0">
                  <Database size={16} className="text-violet-400 shrink-0" />
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-white truncate">{dataset.filename}</p>
                    <p className="text-xs text-[#cbc3d7]">
                      {formatNumber(dataset.row_count)} rows · {formatNumber(dataset.column_count)} columns
                    </p>
                  </div>
                </div>
                <span className="text-[10px] text-emerald-300 bg-emerald-500/10 border border-emerald-500/30 px-2.5 py-1 rounded shrink-0">
                  Connected
                </span>
              </div>
            </GlassCard>
          )}

          {/* Message list */}
          {messages.map((msg) => (
            <motion.div
              key={msg.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3 }}
              className={`flex gap-4 ${
                msg.role === 'user' ? 'self-end max-w-[85%]' : 'self-start w-full max-w-[90%]'
              }`}
            >
              {/* Bot avatar */}
              {msg.role === 'assistant' && (
                <div
                  className={`w-8 h-8 rounded-full bg-gradient-to-br from-violet-500 to-blue-500 shrink-0 mt-1 flex items-center justify-center shadow-md ${
                    msg.isLoading ? 'animate-pulse' : ''
                  }`}
                >
                  <Bot size={16} className="text-white" />
                </div>
              )}

              <div className="flex-1 space-y-3 min-w-0">
                {/* Message bubble */}
                <div
                  className={`${
                    msg.role === 'user'
                      ? 'bg-violet-600/20 border-violet-500/30 rounded-tr-sm'
                      : 'bg-[#171f33]/70 border-[#494454]/30 rounded-tl-sm'
                  } border text-white px-5 py-4 rounded-2xl shadow-sm`}
                >
                  <p className="text-sm leading-relaxed whitespace-pre-wrap">{msg.content}</p>
                </div>

                {/* Loading spinner */}
                {msg.isLoading && (
                  <div className="flex items-center gap-3 px-2">
                    <div className="w-4 h-4 border-2 border-violet-400 border-t-transparent rounded-full animate-spin" />
                    <span className="text-xs text-violet-400 animate-pulse">Analyzing dataset…</span>
                  </div>
                )}

                {/* Warnings */}
                {msg.warnings?.length ? (
                  <GlassCard className="p-4 border-amber-500/20">
                    <div className="flex items-center gap-2 mb-2">
                      <AlertTriangle size={14} className="text-amber-400" />
                      <span className="text-xs font-semibold text-amber-300">Warnings</span>
                    </div>
                    <ul className="space-y-1.5">
                      {msg.warnings.map((w, i) => (
                        <li key={i} className="text-xs text-amber-200/80 leading-relaxed flex gap-2">
                          <span className="text-amber-400/60">•</span> {w}
                        </li>
                      ))}
                    </ul>
                  </GlassCard>
                ) : null}

                {/* Tables */}
                {msg.tables?.map((tbl, i) => (
                  <ResultTable key={`${msg.id}-tbl-${i}`} table={tbl} />
                ))}

                {/* Charts */}
                {msg.charts?.map((chart, i) => (
                  <SimpleChart key={`${msg.id}-chart-${i}`} chart={chart} />
                ))}

                {/* Recommendations */}
                {msg.recommendations?.length ? (
                  <GlassCard className="p-4 border-emerald-500/20">
                    <div className="flex items-center gap-2 mb-3">
                      <Lightbulb size={14} className="text-emerald-300" />
                      <span className="text-xs font-semibold text-emerald-300">Recommendations</span>
                    </div>
                    <ul className="space-y-2">
                      {msg.recommendations.map((rec, i) => (
                        <li key={i} className="text-xs text-[#cbc3d7] leading-relaxed flex gap-2">
                          <CheckCircle2 size={12} className="text-emerald-400 shrink-0 mt-0.5" />
                          {rec}
                        </li>
                      ))}
                    </ul>
                  </GlassCard>
                ) : null}

                {/* Next questions — suggestion chips */}
                {msg.next_questions?.length ? (
                  <div className="flex flex-wrap gap-2 pt-1">
                    {msg.next_questions.map((q) => (
                      <button
                        key={q}
                        type="button"
                        onClick={() => onSubmit(q)}
                        className="text-xs text-violet-200 bg-violet-500/10 border border-violet-500/30 rounded-full px-3 py-1.5 hover:bg-violet-500/20 hover:border-violet-400/50 transition-all"
                      >
                        {q}
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
            </motion.div>
          ))}

          {/* Skeleton loading */}
          {isQuerying && messages.length > 0 && !messages[messages.length - 1]?.isLoading && (
            <div className="flex gap-4 self-start w-full opacity-40">
              <div className="h-16 w-[360px] max-w-full bg-[#171f33] rounded-2xl animate-pulse" />
            </div>
          )}
        </div>
      </div>

      {/* Floating input */}
      <FloatingInput
        onSubmit={onSubmit}
        onFileUpload={onUpload}
        disabled={isQuerying}
        placeholder={dataset ? 'Ask another question...' : 'Upload a dataset first...'}
      />
    </div>
  );
};

// ---------------------------------------------------------------------------
// Main App Component
// ---------------------------------------------------------------------------

export default function App() {
  const [currentView, setCurrentView] = useState<'home' | 'chat'>('home');
  const [dataset, setDataset] = useState<DatasetInfo | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isQuerying, setIsQuerying] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<string | null>(null);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  // ---- File upload handler ----
  const handleUpload = async (file: File) => {
    setUploadStatus(`Uploading ${file.name}…`);

    try {
      const form = new FormData();
      form.append('file', file);

      const res = await fetch(`${API_BASE_URL}/api/datasets/upload`, {
        method: 'POST',
        body: form,
      });

      if (!res.ok) {
        const errorBody = await res.json().catch(() => null);
        throw new Error(errorBody?.detail || `Upload failed (${res.status})`);
      }

      const data = await res.json();

      const info: DatasetInfo = {
        dataset_id: data.dataset_id ?? data.session_id ?? '',
        filename: data.filename ?? data.dataset_filename ?? file.name,
        row_count: data.row_count ?? data.dataset_rows ?? 0,
        column_count: data.column_count ?? data.dataset_cols ?? 0,
        columns: data.columns ?? data.column_names ?? [],
        profile: data.profile ?? data.dataset_profile ?? {},
      };

      setDataset(info);
      setUploadStatus(`${info.filename} uploaded successfully.`);

      // Clear previous conversation on new dataset upload
      setMessages([]);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Upload failed';
      setUploadStatus(msg);
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: `Upload failed: ${msg}`,
        },
      ]);
    }
  };

  // ---- Query / prompt handler ----
  const handleSubmit = async (prompt: string) => {
    if (!dataset) {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          content:
            'Please upload a CSV or Excel file first using the paperclip button, then I can analyze it.',
        },
      ]);
      setCurrentView('chat');
      return;
    }

    const userMsgId = crypto.randomUUID();
    const assistantMsgId = crypto.randomUUID();

    setCurrentView('chat');
    setIsQuerying(true);

    setMessages((prev) => [
      ...prev,
      { id: userMsgId, role: 'user', content: prompt },
      {
        id: assistantMsgId,
        role: 'assistant',
        content: 'Analyzing your dataset…',
        isLoading: true,
      },
    ]);

    try {
      const res = await fetch(`${API_BASE_URL}/api/datasets/${dataset.dataset_id}/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt }),
      });

      if (!res.ok) {
        const errorBody = await res.json().catch(() => null);
        throw new Error(errorBody?.detail || `Request failed (${res.status})`);
      }

      const data = await res.json();

      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantMsgId
            ? {
                ...m,
                content: data.answer ?? data.content ?? data.message ?? 'Analysis complete.',
                tables: data.tables ?? undefined,
                charts: data.charts ?? undefined,
                recommendations: data.recommendations ?? undefined,
                warnings: data.warnings ?? undefined,
                next_questions: data.next_questions ?? data.suggestions ?? undefined,
                isLoading: false,
              }
            : m
        )
      );
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : 'Analysis failed';
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantMsgId
            ? { ...m, content: `Analysis failed: ${errMsg}`, isLoading: false }
            : m
        )
      );
    } finally {
      setIsQuerying(false);
    }
  };

  // ---- Render ----
  return (
    <div className="flex h-screen w-full bg-[#0b1326] text-white font-sans overflow-hidden">
      {/* Desktop Sidebar */}
      <Sidebar
        dataset={dataset}
        currentView={currentView}
        onViewChange={setCurrentView}
      />

      {/* Main content area */}
      <div className="flex-1 flex flex-col relative h-full min-w-0">
        {/* Top header */}
        <header className="absolute top-0 w-full z-40 bg-[#0b1326]/70 backdrop-blur-xl border-b border-[#494454]/30 shadow-sm flex items-center justify-between px-4 md:px-8 h-14">
          <div className="flex items-center gap-4">
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="md:hidden text-[#cbc3d7] hover:text-white"
            >
              <Menu size={22} />
            </button>
            <div className="md:hidden flex items-center gap-2">
              <Sparkles size={16} className="text-violet-400" />
              <span className="text-sm font-bold bg-clip-text text-transparent bg-gradient-to-r from-violet-400 to-blue-400">
                DataVerse AI
              </span>
            </div>
          </div>

          <nav className="hidden md:flex items-center gap-6">
            <button
              onClick={() => setCurrentView('home')}
              className={`text-sm font-medium transition-colors relative pb-1 ${
                currentView === 'home' ? 'text-violet-400' : 'text-[#cbc3d7] hover:text-white'
              }`}
            >
              Home
              {currentView === 'home' && (
                <span className="absolute bottom-0 left-0 w-full h-[2px] bg-violet-400 rounded-t-full" />
              )}
            </button>
            <button
              onClick={() => setCurrentView('chat')}
              className={`text-sm font-medium transition-colors relative pb-1 ${
                currentView === 'chat' ? 'text-violet-400' : 'text-[#cbc3d7] hover:text-white'
              }`}
            >
              Chat
              {currentView === 'chat' && (
                <span className="absolute bottom-0 left-0 w-full h-[2px] bg-violet-400 rounded-t-full" />
              )}
            </button>
          </nav>

          {/* Connection status pill */}
          <div className="flex items-center gap-2 bg-[#171f33]/60 border border-[#494454]/30 px-3 py-1.5 rounded-full">
            <span className="relative flex h-1.5 w-1.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500" />
            </span>
            <span className="text-[10px] text-emerald-300 font-medium">Online</span>
          </div>
        </header>

        {/* Content views */}
        <AnimatePresence mode="wait">
          <motion.div
            key={currentView}
            initial={{ opacity: 0, x: 8 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -8 }}
            transition={{ duration: 0.2 }}
            className="w-full h-full flex flex-col pt-14"
          >
            {currentView === 'home' && (
              <HomeView
                dataset={dataset}
                uploadStatus={uploadStatus}
                onUpload={handleUpload}
                onSubmit={handleSubmit}
              />
            )}
            {currentView === 'chat' && (
              <ChatView
                dataset={dataset}
                messages={messages}
                isQuerying={isQuerying}
                onUpload={handleUpload}
                onSubmit={handleSubmit}
              />
            )}
          </motion.div>
        </AnimatePresence>
      </div>

      {/* Mobile bottom nav */}
      <MobileNav currentView={currentView} onViewChange={setCurrentView} />
    </div>
  );
}
