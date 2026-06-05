'use client';

import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { 
  Menu, History, Database, FolderOpen, Settings, Bot, Table, Layers, 
  Hash, List, Calendar, AlertTriangle, Sparkles, 
  Paperclip, ArrowRight, ArrowUp, BarChart2, Store, BrainCircuit, 
  Brain, CheckCircle2, TrendingUp, Plus, FileSpreadsheet, Eye, 
  ShoppingCart, CloudUpload, MessageSquare, FileText,
  ShieldCheck, Lock, Server, Users, Target, Briefcase
} from 'lucide-react';
import {
  API_BASE_URL,
  analyzeSession,
  createSession,
  getSession,
  listDatasets,
  listSessions,
  streamQuery,
  uploadDataset,
  type ChartPayload,
  type ChatEvent,
  type ChatSessionSummary,
  type RecentDataset,
  type TablePayload,
  type UploadResponse,
} from '@/lib/dataverse-api';

// --- Shared Constants & Types ---
type ViewState = 'landing' | 'signup' | 'signin' | 'home' | 'chat' | 'data';
type ChatRole = 'user' | 'assistant' | 'system';

type ChatMessage = {
  id: string;
  role: ChatRole;
  content: string;
  events?: ChatEvent[];
  charts?: ChartPayload[];
  tables?: TablePayload[];
  recommendations?: string[];
  suggestions?: string[];
  report?: {
    report_id: string;
    html_url?: string;
    pdf_url?: string;
  } | null;
  isLoading?: boolean;
};

type DatasetSummary = UploadResponse & {
  originalFileSize?: number;
};

const datasetFromRecent = (item: RecentDataset): DatasetSummary => {
  const columns = Array.isArray(item.columns)
    ? item.columns as Array<{ name?: string; dtype?: string } | string>
    : [];
  return {
    session_id: item.session_id,
    success: true,
    message: 'Dataset loaded from saved session.',
    is_retail: false,
    dataset_id: item.id,
    dataset_filename: item.filename || item.original_filename || 'Untitled dataset',
    dataset_rows: item.row_count,
    dataset_cols: item.column_count,
    column_names: columns.map((column) => typeof column === 'string' ? column : column.name || ''),
    column_dtypes: columns.map((column) => typeof column === 'string' ? '' : column.dtype || ''),
    dataset_profile: item.schema_profile as DatasetSummary['dataset_profile'],
    dataset_type: (item.schema_profile as { dataset_type?: string } | undefined)?.dataset_type,
    created_at: item.created_at,
  };
};

const USER_AVATAR = "https://lh3.googleusercontent.com/aida-public/AB6AXuCSVDlpno8RznSfi8aRBuArVUJU-R1S27kFBXpAQaWPIVRxiX3eu3JP_JwYidrzi372kezOq0YvbKnESGiPFioraWolHTGZ2p1A5wcnZMKBYj2c0TjbM1aZiwOvR7ickXREMohaal629tR8QYSXX81egHtyiNOdxoHVBSpWZO8gYqBxfE327WUidqb27GQLpC0yuKHmKF3HQGuyvsv7IuFNF1uR24oUNvMcsnyxmv_eb6G4oZHL-BSNO2Zs5BMJpvRB99H_rnvkcZ8";
const BOT_AVATAR = <Bot size={18} className="text-white" />;

const formatNumber = (value?: number) => {
  if (typeof value !== 'number') return '0';
  return new Intl.NumberFormat('en-US', { notation: value > 9999 ? 'compact' : 'standard' }).format(value);
};

const formatFileSize = (bytes?: number) => {
  if (!bytes) return 'n/a';
  const units = ['B', 'KB', 'MB', 'GB'];
  let size = bytes;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size.toFixed(size >= 10 || unit === 0 ? 0 : 1)} ${units[unit]}`;
};

const isNumericType = (dtype?: string) => {
  const normalized = dtype?.toLowerCase() ?? '';
  return ['int', 'float', 'double', 'number', 'decimal'].some((needle) => normalized.includes(needle));
};

const formatCell = (value: unknown) => {
  if (value === null || value === undefined || value === '') return 'ÔÇö';
  if (typeof value === 'number') return new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 }).format(value);
  return String(value);
};

const datasetTypeOf = (dataset: DatasetSummary | null) => dataset?.dataset_type || String(dataset?.dataset_profile?.dataset_type || 'generic');

const datasetTypeLabel = (dataset: DatasetSummary | null) => {
  const type = datasetTypeOf(dataset);
  return type.split('_').map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(' ');
};

const datasetSuggestions = (dataset: DatasetSummary | null) => {
  const type = datasetTypeOf(dataset);
  const semantic = (dataset?.dataset_profile?.semantic_columns ?? {}) as Record<string, unknown>;
  if (type === 'business_leads') {
    return [
      semantic.country ? 'Which countries have the most businesses?' : null,
      semantic.industry ? 'Which industries are most common?' : null,
      'Which businesses look like the highest-value leads?',
      semantic.employee_range ? 'Segment businesses by employee range.' : null,
      semantic.revenue_range ? 'Segment businesses by yearly revenue range.' : null,
      'Create an outreach strategy for these leads.',
      semantic.website ? 'Which businesses have no website?' : null,
    ].filter(Boolean) as string[];
  }
  if (type === 'sales') {
    return [
      semantic.product ? 'What are the top products?' : null,
      semantic.product && semantic.date ? 'Which products are trending?' : null,
      semantic.revenue && semantic.date ? 'Show revenue by month.' : null,
      semantic.category ? 'Which category performs best?' : null,
    ].filter(Boolean) as string[];
  }
  return ['Summarize this dataset.', 'Which columns have missing values?', 'Show unique values by column.', 'Find important patterns.'];
};

// --- Components ---

const GlassCard = ({ children, className = '', onClick }: { children: React.ReactNode, className?: string, onClick?: () => void }) => (
  <div 
    onClick={onClick}
    className={`bg-[#171f33]/60 backdrop-blur-xl border border-[#494454]/30 rounded-xl overflow-hidden ${onClick ? 'cursor-pointer hover:border-violet-500/50 hover:shadow-[0_0_20px_rgba(139,92,246,0.15)] transition-all duration-300' : ''} ${className}`}
  >
    {children}
  </div>
);

const FloatingInput = ({
  onSubmit,
  onFileUpload,
  disabled = false,
  placeholder = 'Message DataVerse AI...',
  className = "absolute bottom-24 md:bottom-8 left-0 w-full px-4 md:px-8 z-30 pointer-events-none",
}: {
  onSubmit: (t: string) => void;
  onFileUpload?: (file: File) => void;
  disabled?: boolean;
  placeholder?: string;
  className?: string;
}) => {
  const [text, setText] = useState('');
  const submit = () => {
    if (disabled || !text.trim()) return;
    onSubmit(text.trim());
    setText('');
  };
  
  return (
    <div className={className}>
      <div className="max-w-[800px] mx-auto relative pointer-events-auto group">
        <div className="absolute inset-0 bg-gradient-to-r from-violet-500/10 to-blue-500/10 blur-2xl rounded-full translate-y-2 group-focus-within:from-violet-500/20 group-focus-within:to-blue-500/20 transition-all duration-500"></div>
        <div className="relative bg-[#2d3449]/90 backdrop-blur-2xl border border-[#494454]/60 rounded-[2rem] p-2 xl:p-2.5 shadow-2xl flex items-end gap-2 focus-within:border-violet-400/60 focus-within:bg-[#2d3449] transition-all">
          <label className={`p-3 text-[#cbc3d7] hover:text-white transition-colors hover:bg-white/5 rounded-full shrink-0 ${onFileUpload ? 'cursor-pointer' : 'opacity-50 cursor-not-allowed'}`} title="Upload CSV or Excel">
            <input
              type="file"
              accept=".csv,.xlsx,.xls"
              className="hidden"
              disabled={!onFileUpload || disabled}
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file && onFileUpload) {
                  onFileUpload(file);
                }
                event.target.value = '';
              }}
            />
            <Paperclip size={20} />
          </label>
          
          <div className="flex-1 py-1">
            <textarea 
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
          
          <button 
            onClick={submit}
            disabled={disabled || !text.trim()}
            className="p-3 bg-gradient-to-br from-violet-400 to-blue-400 text-[#0b1326] rounded-full shrink-0 flex items-center justify-center hover:brightness-110 active:scale-95 transition-all shadow-sm disabled:opacity-50 disabled:grayscale"
          >
            <ArrowUp size={20} />
          </button>
        </div>
        <div className="text-center mt-2">
          <span className="text-[10px] text-[#cbc3d7]/60">DataVerse AI can make mistakes. Verify important data.</span>
        </div>
      </div>
    </div>
  );
};

const ResultTable = ({ table }: { table: TablePayload }) => (
  <GlassCard className="overflow-hidden border-slate-500/20">
    <div className="flex items-center gap-3 px-4 py-3 border-b border-[#494454]/40 bg-[#0b1326]/40">
      <Table size={16} className="text-violet-300" />
      <span className="text-sm font-medium text-white">{table.title}</span>
    </div>
    <div className="overflow-x-auto">
      <table className="w-full text-left text-xs">
        <thead className="bg-[#131b2e] text-[#cbc3d7]">
          <tr>
            {table.columns.map((column) => (
              <th key={column} className="px-4 py-3 font-semibold whitespace-nowrap">{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.slice(0, 10).map((row, index) => (
            <tr key={index} className="border-t border-[#494454]/30 text-slate-100">
              {table.columns.map((column) => (
                <td key={column} className="px-4 py-3 whitespace-nowrap">{formatCell(row[column])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  </GlassCard>
);

const SimpleChart = ({ chart }: { chart: ChartPayload }) => {
  const yKey = chart.y_key;
  const values = yKey ? chart.data.map((row) => Number(row[yKey]) || 0) : [];
  const max = Math.max(...values.map((value) => Math.abs(value)), 1);

  if (chart.type === 'line' && yKey) {
    const width = 520;
    const height = 180;
    const points = values.map((value, index) => {
      const x = values.length === 1 ? width / 2 : (index / (values.length - 1)) * width;
      const y = height - ((value / max) * (height - 20) + 10);
      return `${x},${Math.max(8, Math.min(height - 8, y))}`;
    }).join(' ');

    return (
      <GlassCard className="p-4 border-blue-500/20">
        <div className="flex items-center gap-3 mb-4">
          <BarChart2 size={16} className="text-blue-400" />
          <span className="text-sm font-medium text-white">{chart.title}</span>
        </div>
        <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-48 overflow-visible">
          <polyline fill="none" stroke="#60a5fa" strokeWidth="3" points={points} />
          {values.map((value, index) => {
            const [x, y] = points.split(' ')[index].split(',').map(Number);
            return <circle key={index} cx={x} cy={y} r="4" fill="#a78bfa" />;
          })}
        </svg>
        <div className="flex justify-between gap-3 text-[10px] text-[#cbc3d7]">
          {chart.data.slice(0, 6).map((row, index) => <span key={index} className="truncate">{formatCell(row[chart.x_key])}</span>)}
        </div>
      </GlassCard>
    );
  }

  if (yKey) {
    return (
      <GlassCard className="p-4 border-blue-500/20">
        <div className="flex items-center gap-3 mb-4">
          <BarChart2 size={16} className="text-blue-400" />
          <span className="text-sm font-medium text-white">{chart.title}</span>
        </div>
        <div className="space-y-3">
          {chart.data.slice(0, 10).map((row, index) => {
            const raw = Number(row[yKey]) || 0;
            const width = `${Math.max(4, Math.min(100, Math.abs(raw) / max * 100))}%`;
            return (
              <div key={index} className="grid grid-cols-[minmax(96px,180px)_1fr_72px] items-center gap-3">
                <span className="text-xs text-[#cbc3d7] truncate">{formatCell(row[chart.x_key])}</span>
                <div className="h-2.5 rounded-full bg-[#222a3d] overflow-hidden">
                  <div className={`h-full rounded-full ${raw < 0 ? 'bg-rose-400' : 'bg-blue-400'}`} style={{ width }} />
                </div>
                <span className="text-xs font-mono text-white text-right">{formatCell(raw)}</span>
              </div>
            );
          })}
        </div>
      </GlassCard>
    );
  }

  return null;
};

// --- Views ---

const LandingView = ({ onNavigate }: { onNavigate: (v: ViewState) => void }) => {
  const productOutcomes = [
    { icon: CloudUpload, title: 'Upload messy files', desc: 'CSV and Excel data is profiled, typed, and prepared for questions.' },
    { icon: MessageSquare, title: 'Ask in plain English', desc: 'Request summaries, charts, forecasts, segments, and follow-up analysis.' },
    { icon: BrainCircuit, title: 'Understand the why', desc: 'Explainable AI highlights drivers, confidence, and model reasoning.' },
    { icon: FileText, title: 'Share the answer', desc: 'Turn findings into clean reports and reusable decision notes.' },
  ];

  const operatingLoop = [
    { label: 'Profile', detail: 'Detects columns, missing values, duplicate rows, and business meaning.' },
    { label: 'Plan', detail: 'Routes the request to EDA, visualization, AutoML, XAI, or reporting tools.' },
    { label: 'Analyze', detail: 'Runs grounded calculations and returns charts, tables, and narrative.' },
    { label: 'Improve', detail: 'Suggests smart follow-up questions based on the dataset type.' },
  ];

  return (
    <div className="h-screen bg-slate-950 text-white font-sans selection:bg-violet-500/30 overflow-x-hidden overflow-y-auto scroll-smooth">
      {/* Navbar */}
      <nav className="fixed top-0 w-full z-50 border-b border-slate-800/50 bg-slate-950/80 backdrop-blur-xl">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Sparkles className="text-violet-400" size={20} />
            <span className="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-violet-500 to-blue-500">
              DataVerse AI
            </span>
          </div>
          <div className="hidden md:flex items-center gap-8 text-sm font-medium text-slate-300">
            <a href="#what-it-does" className="hover:text-white transition-colors">What it does</a>
            <a href="#features" className="hover:text-white transition-colors">Features</a>
            <a href="#engine" className="hover:text-white transition-colors">Engine</a>
            <a href="#security" className="hover:text-white transition-colors">Security</a>
            <a href="#docs" className="hover:text-white transition-colors">Docs</a>
          </div>
          <div className="flex items-center gap-4">
            <button onClick={() => onNavigate('signin')} className="text-sm font-medium text-slate-300 hover:text-white transition-colors hidden sm:block">
              Sign In
            </button>
            <button onClick={() => onNavigate('signup')} className="bg-gradient-to-r from-violet-500 to-blue-500 text-white px-5 py-2 rounded-lg text-sm font-medium hover:brightness-110 transition-all active:scale-95 shadow-[0_0_15px_rgba(139,92,246,0.4)]">
              Get Started
            </button>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="pt-32 pb-20 px-6 max-w-7xl mx-auto flex flex-col items-center text-center relative">
        <div className="absolute top-20 left-1/4 w-96 h-96 bg-violet-600/20 rounded-full blur-[120px] pointer-events-none" />
        <div className="absolute top-40 right-1/4 w-96 h-96 bg-blue-600/20 rounded-full blur-[120px] pointer-events-none" />

        <div className="relative z-10 max-w-4xl">
          <h1 className="text-5xl md:text-7xl font-bold tracking-tight mb-6 leading-tight">
            Chat with your data. <br/>
            <span className="bg-clip-text text-transparent bg-gradient-to-r from-violet-400 to-blue-400">Uncover instant insights.</span>
          </h1>
          <p className="text-lg md:text-xl text-slate-400 mb-10 max-w-2xl mx-auto leading-relaxed">
            An enterprise-grade analytics platform powered by a focused analysis core and explainable AI. Upload your CSV, ask natural language questions, and get interactive charts, AutoML models, and grounded answers in seconds.
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <button onClick={() => onNavigate('signup')} className="flex items-center justify-center gap-2 bg-gradient-to-r from-violet-500 to-blue-500 text-white px-8 py-4 rounded-xl text-base font-medium hover:brightness-110 transition-all active:scale-95 shadow-[0_0_20px_rgba(139,92,246,0.4)] w-full sm:w-auto">
              Start Analyzing <ArrowRight size={18} />
            </button>
            <button onClick={() => onNavigate('home')} className="flex items-center justify-center gap-2 bg-slate-900/50 border border-slate-700 text-white px-8 py-4 rounded-xl text-base font-medium hover:bg-slate-800 transition-all active:scale-95 w-full sm:w-auto">
              Continue as Guest
            </button>
          </div>
          <div className="mt-10 grid grid-cols-1 sm:grid-cols-3 gap-3 text-left">
            {[
              ['No setup', 'Start with a spreadsheet'],
              ['Grounded answers', 'Charts and tables included'],
              ['Explainable models', 'Drivers you can defend'],
            ].map(([title, desc]) => (
              <div key={title} className="rounded-xl border border-slate-800 bg-slate-900/40 px-4 py-3">
                <div className="text-sm font-semibold text-white">{title}</div>
                <div className="text-xs text-slate-500 mt-1">{desc}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Hero Visual - Chat Mockup */}
        <div className="mt-16 w-full max-w-5xl relative z-10 text-left">
          <div className="bg-slate-900/90 backdrop-blur-xl border border-slate-700/70 rounded-2xl shadow-2xl shadow-violet-950/20 overflow-hidden flex h-[500px]">
            {/* Sidebar */}
            <div className="hidden md:flex w-64 bg-slate-950/50 border-r border-slate-800 flex-col p-4 shrink-0">
              <div className="flex items-center gap-2 mb-8 px-2 mt-2">
                <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-violet-500 to-blue-500 flex items-center justify-center shadow-inner">
                  <Bot size={16} className="text-white"/>
                </div>
                <span className="font-semibold tracking-tight">DataVerse</span>
              </div>
              <div className="space-y-1">
                <div className="bg-slate-800/80 text-slate-200 px-3 py-2 rounded-lg text-sm font-medium border border-slate-700/50 flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" /> Active Analysis
                </div>
                <div className="text-slate-500 hover:text-slate-300 px-3 py-2 rounded-lg text-sm transition-colors cursor-pointer flex items-center gap-2">
                  <Database size={14} /> Uploaded Dataset
                </div>
                <div className="text-slate-500 hover:text-slate-300 px-3 py-2 rounded-lg text-sm transition-colors cursor-pointer flex items-center gap-2">
                  <Database size={14} /> Generated Report
                </div>
              </div>
            </div>

            {/* Chat Area */}
            <div className="flex-1 p-6 flex flex-col gap-6 overflow-hidden relative">
              {/* Fake header inside chat */}
              <div className="absolute top-0 left-0 w-full h-24 bg-gradient-to-b from-slate-900/80 to-transparent z-10 pointer-events-none" />
              
              <div className="flex-1 overflow-y-auto space-y-6 pb-6 pt-2 pr-2 custom-scrollbar">
                <div className="flex gap-4 self-end max-w-[85%] ml-auto">
                  <div className="bg-violet-600/20 border border-violet-500/30 text-white px-4 py-3 rounded-2xl rounded-tr-sm text-sm shadow-sm">
                    Analyze sales trends for the last 4 quarters and break them down by region.
                  </div>
                </div>
                
                <div className="flex gap-4 self-start max-w-[95%] w-full">
                  <div className="w-8 h-8 rounded-full bg-gradient-to-br from-violet-500 to-blue-500 flex shrink-0 items-center justify-center shadow-[0_0_10px_rgba(139,92,246,0.3)] mt-1">
                    <Sparkles size={14} className="text-white" />
                  </div>
                  <div className="flex-1 space-y-4">
                    <div className="flex items-center gap-2 text-sm text-slate-400 mt-1.5">
                      <span className="flex h-2 w-2 relative">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-violet-400 opacity-75"></span>
                        <span className="relative inline-flex rounded-full h-2 w-2 bg-violet-500"></span>
                      </span>
                      Analyzing dataset...
                    </div>
                    
                    <div className="bg-[#0b1326] border border-slate-800 rounded-xl p-5 shadow-inner">
                      <div className="flex justify-between items-center mb-6">
                        <span className="text-sm font-medium text-slate-200">Quarterly Sales by Region</span>
                        <div className="flex gap-3 text-xs text-slate-400">
                          <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded bg-violet-500"></span> NA</span>
                          <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded bg-blue-500"></span> EU</span>
                          <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded bg-sky-500"></span> APAC</span>
                        </div>
                      </div>
                      
                      {/* Fake Plotly Chart */}
                      <div className="flex items-end justify-between h-40 border-l border-b border-slate-800 pb-0 pt-4 px-2 xl:px-8">
                        <div className="flex-1 flex justify-center items-end gap-1"><div className="w-4 sm:w-6 lg:w-8 bg-violet-500 h-[40%] rounded-t-sm"></div><div className="w-4 sm:w-6 lg:w-8 bg-blue-500 h-[30%] rounded-t-sm"></div><div className="w-4 sm:w-6 lg:w-8 bg-sky-500 h-[50%] rounded-t-sm"></div></div>
                        <div className="flex-1 flex justify-center items-end gap-1"><div className="w-4 sm:w-6 lg:w-8 bg-violet-500 h-[60%] rounded-t-sm"></div><div className="w-4 sm:w-6 lg:w-8 bg-blue-500 h-[45%] rounded-t-sm"></div><div className="w-4 sm:w-6 lg:w-8 bg-sky-500 h-[65%] rounded-t-sm"></div></div>
                        <div className="flex-1 flex justify-center items-end gap-1"><div className="w-4 sm:w-6 lg:w-8 bg-violet-500 h-[85%] rounded-t-sm"></div><div className="w-4 sm:w-6 lg:w-8 bg-blue-500 h-[70%] rounded-t-sm"></div><div className="w-4 sm:w-6 lg:w-8 bg-sky-500 h-[90%] rounded-t-sm"></div></div>
                        <div className="flex-1 flex justify-center items-end gap-1"><div className="w-4 sm:w-6 lg:w-8 bg-violet-500 h-[100%] rounded-t-sm relative">
                           {/* Tooltip mockup */}
                           <div className="absolute -top-10 left-1/2 -translate-x-1/2 bg-slate-800 text-white text-[10px] py-1 px-2 rounded opacity-0 lg:opacity-100 whitespace-nowrap border border-slate-700 shadow-xl pointer-events-none">
                              $2.4M (NA)
                           </div>
                        </div><div className="w-4 sm:w-6 lg:w-8 bg-blue-500 h-[80%] rounded-t-sm"></div><div className="w-4 sm:w-6 lg:w-8 bg-sky-500 h-[95%] rounded-t-sm"></div></div>
                      </div>
                      <div className="flex justify-between px-2 xl:px-8 mt-3 text-[11px] font-medium text-slate-500 uppercase tracking-wider">
                        <span className="flex-1 text-center">Q1</span>
                        <span className="flex-1 text-center">Q2</span>
                        <span className="flex-1 text-center">Q3</span>
                        <span className="flex-1 text-center">Q4</span>
                      </div>
                    </div>
                    
                    <p className="text-sm text-slate-300 leading-relaxed font-light">
                      I have grouped the sales data by quarter and region. We&apos;re seeing a consistent upward trend, particularly in Q4 where North America dominates the revenue share at $2.4M. Would you like me to build a forecasting model based on this trajectory?
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* What it does */}
      <section id="what-it-does" className="py-24 px-6 max-w-7xl mx-auto relative z-10 border-t border-slate-800/50">
        <div className="grid grid-cols-1 lg:grid-cols-[0.9fr_1.1fr] gap-10 lg:gap-16 items-start">
          <div>
            <h2 className="text-3xl md:text-4xl font-bold tracking-tight mb-5">What DataVerse AI does</h2>
            <p className="text-slate-400 text-lg leading-relaxed mb-8">
              DataVerse AI turns raw business data into a guided analysis workspace. It profiles your file, chooses the right analysis path, creates visuals, explains model behavior, and helps you move from question to decision without switching tools.
            </p>
            <div className="grid grid-cols-2 gap-4">
              {[
                ['CSV/XLSX', 'Upload support'],
                ['EDA + ML', 'Analysis modes'],
                ['SHAP/LIME', 'Explainability'],
                ['Reports', 'Shareable output'],
              ].map(([value, label]) => (
                <div key={value} className="border-l border-violet-500/60 pl-4 py-1">
                  <div className="text-2xl font-semibold text-white tracking-tight">{value}</div>
                  <div className="text-xs text-slate-500 mt-1 uppercase tracking-wider">{label}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
            {productOutcomes.map((item, index) => (
              <motion.div
                key={item.title}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: index * 0.08 }}
                className="group bg-slate-900/40 border border-slate-800/80 rounded-2xl p-6 text-left hover:bg-slate-900 hover:border-violet-500/50 transition-all duration-300"
              >
                <div className="w-11 h-11 rounded-xl bg-slate-800/60 border border-slate-700/60 flex items-center justify-center mb-5">
                  <item.icon size={22} className="text-violet-400 group-hover:text-blue-400 transition-colors" />
                </div>
                <h3 className="text-lg font-semibold text-white mb-2 tracking-tight">{item.title}</h3>
                <p className="text-sm text-slate-400 leading-relaxed">{item.desc}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* Features Grid */}
      <section id="features" className="py-24 px-6 max-w-7xl mx-auto relative z-10">
        <div className="text-center mb-16">
          <h2 className="text-3xl md:text-4xl font-bold mb-4 tracking-tight">The Analysis Engine</h2>
          <p className="text-slate-400 text-lg max-w-2xl mx-auto">A focused analysis agent and XAI agent validate, process, and explain your data securely.</p>
        </div>
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {[
            { icon: BarChart2, title: 'Autonomous EDA', desc: 'Upload a dataset and instantly get missing value analysis, distributions, and correlation heatmaps.' },
            { icon: Brain, title: 'One-Click AutoML', desc: 'Train classification and regression models automatically in the background using Scikit-Learn integration.' },
            { icon: Eye, title: 'SHAP & LIME Explanations', desc: 'Never guess why a model made a decision. Get local and global feature importance on demand.' },
            { icon: ShoppingCart, title: 'Universal Dataset Routing', desc: 'Classify sales, finance, customer, business leads, and generic datasets without rejecting non-retail files.' }
          ].map((feat, i) => (
            <motion.div 
              key={feat.title}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.1 }}
              className="group bg-slate-900/40 backdrop-blur-sm border border-slate-800/80 p-8 rounded-2xl hover:bg-slate-900/80 hover:border-violet-500/50 hover:shadow-[0_0_30px_rgba(139,92,246,0.1)] transition-all duration-300 relative overflow-hidden text-left"
            >
              <div className="absolute -top-20 -right-20 w-48 h-48 bg-violet-500/10 rounded-full blur-[50px] opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none" />
              <div className="w-12 h-12 bg-slate-800/50 border border-slate-700/50 rounded-xl flex items-center justify-center mb-6 group-hover:scale-110 group-hover:bg-slate-800 transition-all duration-300 shadow-inner">
                <feat.icon className="text-violet-400" size={24} />
              </div>
              <h3 className="text-xl font-semibold mb-3 tracking-tight">{feat.title}</h3>
              <p className="text-slate-400 leading-relaxed text-sm">{feat.desc}</p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* How it Works */}
      <section id="engine" className="py-24 px-6 max-w-7xl mx-auto relative z-10 border-t border-slate-800/50">
        <div className="text-center mb-16">
          <h2 className="text-3xl md:text-4xl font-bold mb-4 tracking-tight">How it works</h2>
          <p className="text-slate-400 text-lg max-w-2xl mx-auto">From raw data to actionable insights in three simple steps.</p>
        </div>
        
        <div className="flex flex-col md:flex-row gap-8 lg:gap-16 items-start justify-center relative">
          {/* connecting line */}
          <div className="hidden md:block absolute top-[45px] left-[15%] right-[15%] h-[2px] bg-gradient-to-r from-transparent via-slate-700 to-transparent z-0 pointer-events-none" />
          
          {[
            { icon: CloudUpload, title: 'Drop your Dataset', desc: 'Upload CSV, Excel, or connect directly to your SQL warehouse.', step: '01' },
            { icon: MessageSquare, title: 'Ask Anything', desc: 'Use natural language to query, create charts, or train models.', step: '02' },
            { icon: FileText, title: 'Export Reports', desc: 'Generate and share HTML, DOCX, or Markdown reports instantly.', step: '03' }
          ].map((step, i) => (
            <motion.div 
              key={step.step} 
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.15 }}
              className="flex-1 flex flex-col items-center text-center relative z-10 w-full"
            >
              <div className="bg-slate-950 px-4">
                <div className="w-[90px] h-[90px] rounded-full bg-slate-900 border-2 border-slate-800 flex items-center justify-center mb-6 relative group hover:border-violet-500/50 transition-colors shadow-xl">
                  <div className="absolute inset-2 rounded-full border border-dashed border-slate-700/50 group-hover:animate-[spin_4s_linear_infinite]" />
                  <step.icon size={28} className="text-blue-400 relative z-10 group-hover:scale-110 transition-transform" />
                </div>
              </div>
              <div className="text-xs font-bold text-violet-400 mb-3 mt-2 tracking-[0.2em]">{step.step}</div>
              <h3 className="text-xl font-semibold mb-3 tracking-tight">{step.title}</h3>
              <p className="text-slate-400 text-sm leading-relaxed max-w-xs">{step.desc}</p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* Operating Loop */}
      <section className="py-24 px-6 max-w-7xl mx-auto relative z-10 border-t border-slate-800/50">
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_1.2fr] gap-10 lg:gap-14 items-center">
          <div>
            <h2 className="text-3xl md:text-4xl font-bold mb-5 tracking-tight">Built like an analyst team</h2>
            <p className="text-slate-400 text-lg leading-relaxed">
              Instead of returning one generic answer, DataVerse AI runs a structured analysis loop: it checks the data, chooses tools, explains the output, and recommends the next useful question.
            </p>
          </div>
          <div className="rounded-2xl border border-slate-800/80 bg-slate-900/40 overflow-hidden">
            {operatingLoop.map((item, index) => (
              <div key={item.label} className="grid grid-cols-[72px_1fr] gap-5 px-5 sm:px-7 py-5 border-b border-slate-800/70 last:border-b-0">
                <div className="flex items-start gap-3">
                  <span className="text-xs font-semibold text-violet-400 tracking-wider">{String(index + 1).padStart(2, '0')}</span>
                  <span className="mt-1 h-2 w-2 rounded-full bg-blue-400 shadow-[0_0_12px_rgba(96,165,250,0.8)]" />
                </div>
                <div>
                  <h3 className="text-base font-semibold text-white">{item.label}</h3>
                  <p className="text-sm text-slate-400 mt-1 leading-relaxed">{item.detail}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Use Cases Section */}
      <section className="py-24 px-6 max-w-7xl mx-auto relative z-10 border-t border-slate-800/50">
        <div className="text-center mb-16">
          <h2 className="text-3xl md:text-4xl font-bold mb-4 tracking-tight">Built for every team</h2>
          <p className="text-slate-400 text-lg max-w-2xl mx-auto">Empower your entire organization with AI-driven insights.</p>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
           {[
             { icon: TrendingUp, title: 'Sales & Revenue', desc: 'Forecast pipeline and analyze win/loss trends instantly.' },
             { icon: Users, title: 'Marketing', desc: 'Uncover customer segments and optimize campaign ROI.' },
             { icon: Target, title: 'Product', desc: 'Track feature adoption and predict user churn automatically.' },
             { icon: Briefcase, title: 'Finance', desc: 'Automate expense categorization and variance analysis.' }
           ].map((uc, i) => (
             <motion.div 
               initial={{ opacity: 0, y: 20 }}
               whileInView={{ opacity: 1, y: 0 }}
               viewport={{ once: true }}
               transition={{ delay: i * 0.1 }}
               key={uc.title} 
               className="p-8 rounded-2xl border border-slate-800/80 bg-slate-900/40 hover:bg-slate-900 hover:border-blue-500/50 hover:shadow-[0_0_30px_rgba(59,130,246,0.1)] transition-all duration-300 text-left"
             >
                <div className="w-12 h-12 bg-slate-800/50 border border-slate-700/50 rounded-xl flex items-center justify-center mb-6 shadow-inner">
                  <uc.icon className="text-blue-400" size={24} />
                </div>
                <h3 className="text-lg font-semibold mb-3 tracking-tight">{uc.title}</h3>
                <p className="text-slate-400 text-sm leading-relaxed">{uc.desc}</p>
             </motion.div>
           ))}
        </div>
      </section>

      {/* Security Section */}
      <section id="security" className="py-24 px-6 max-w-7xl mx-auto relative z-10 border-t border-slate-800/50">
        <div className="text-center mb-16">
          <h2 className="text-3xl md:text-4xl font-bold mb-4 tracking-tight">Enterprise-Grade Security</h2>
          <p className="text-slate-400 text-lg max-w-2xl mx-auto">Your data never trains our models. Deploy with confidence in a secure environment.</p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {[
            { icon: ShieldCheck, title: 'SOC 2 Type II Compliant', desc: 'Audited and certified for the highest standards of data security and privacy.' },
            { icon: Lock, title: 'End-to-End Encryption', desc: 'Data is encrypted at rest and in transit using AES-256 and TLS 1.3 protocols.' },
            { icon: Server, title: 'Private VPC Deployment', desc: 'Host DataVerse AI within your own cloud infrastructure for ultimate control.' }
          ].map((item, i) => (
             <motion.div 
               initial={{ opacity: 0, y: 20 }}
               whileInView={{ opacity: 1, y: 0 }}
               viewport={{ once: true }}
               transition={{ delay: i * 0.1 }}
               key={item.title} 
               className="bg-slate-900/40 border border-slate-800/80 p-8 rounded-2xl flex flex-col items-center text-center hover:bg-slate-900 hover:border-emerald-500/50 hover:shadow-[0_0_30px_rgba(16,185,129,0.1)] transition-all duration-300"
             >
              <div className="w-14 h-14 bg-slate-800/50 border border-slate-700/50 rounded-xl flex items-center justify-center mb-6 shadow-inner">
                <item.icon className="text-emerald-400" size={28} />
              </div>
              <h3 className="text-xl font-semibold mb-3 tracking-tight">{item.title}</h3>
              <p className="text-sm text-slate-400 leading-relaxed">{item.desc}</p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* Final CTA */}
      <section className="py-20 px-6 max-w-7xl mx-auto relative z-10 border-t border-slate-800/50">
        <div className="rounded-2xl border border-slate-800 bg-slate-900/50 px-6 py-10 sm:px-10 sm:py-12 flex flex-col lg:flex-row lg:items-center justify-between gap-8 overflow-hidden relative">
          <div className="absolute inset-0 bg-gradient-to-r from-violet-500/10 via-transparent to-blue-500/10 pointer-events-none" />
          <div className="relative z-10 max-w-2xl">
            <h2 className="text-3xl md:text-4xl font-bold tracking-tight mb-4">Ready to turn your next file into a decision?</h2>
            <p className="text-slate-400 leading-relaxed">
              Start with a spreadsheet, ask a real business question, and let DataVerse AI build the analysis path around your data.
            </p>
          </div>
          <div className="relative z-10 flex flex-col sm:flex-row gap-3">
            <button onClick={() => onNavigate('signup')} className="flex items-center justify-center gap-2 bg-gradient-to-r from-violet-500 to-blue-500 text-white px-6 py-3 rounded-xl text-sm font-medium hover:brightness-110 transition-all active:scale-95 shadow-[0_0_20px_rgba(139,92,246,0.25)]">
              Create Workspace <ArrowRight size={17} />
            </button>
            <button onClick={() => onNavigate('home')} className="flex items-center justify-center gap-2 bg-slate-950/50 border border-slate-700 text-white px-6 py-3 rounded-xl text-sm font-medium hover:bg-slate-900 transition-all active:scale-95">
              Try Guest Mode
            </button>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer id="docs" className="border-t border-slate-800/80 bg-slate-950 py-12 px-6 relative z-10">
        <div className="max-w-7xl mx-auto grid grid-cols-1 md:grid-cols-[1.2fr_0.8fr_0.8fr_1fr] gap-8">
          <div>
            <div className="flex items-center gap-2">
              <Sparkles className="text-violet-400" size={18} />
              <span className="font-bold text-slate-200 tracking-tight text-lg">DataVerse AI</span>
            </div>
            <p className="text-sm text-slate-500 leading-relaxed mt-4 max-w-sm">
              An AI analytics workspace for datasets, charts, explainable models, and shareable business reports.
            </p>
          </div>

          <div>
            <h3 className="text-xs font-semibold text-slate-300 uppercase tracking-wider mb-4">Product</h3>
            <div className="space-y-3 text-sm text-slate-500">
              <a href="#what-it-does" className="block hover:text-slate-300 transition-colors">What it does</a>
              <a href="#features" className="block hover:text-slate-300 transition-colors">Features</a>
              <a href="#engine" className="block hover:text-slate-300 transition-colors">Engine</a>
            </div>
          </div>

          <div>
            <h3 className="text-xs font-semibold text-slate-300 uppercase tracking-wider mb-4">Use cases</h3>
            <div className="space-y-3 text-sm text-slate-500">
              <span className="block">Sales analytics</span>
              <span className="block">Customer insights</span>
              <span className="block">Finance reporting</span>
            </div>
          </div>

          <div className="space-y-4">
            <div className="flex items-center gap-2.5 bg-slate-900 border border-slate-800 px-4 py-2 rounded-full text-xs font-medium text-slate-300 shadow-sm w-fit">
              <span className="relative flex h-2 w-2">
                 <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                 <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
              </span>
              Analysis Core Operational
            </div>
            <p className="text-sm text-slate-500">&copy; {new Date().getFullYear()} All rights reserved by inventacore.org</p>
          </div>
        </div>
      </footer>
    </div>
  );
};

const SignUpView = ({ onComplete, onSwitchToSignIn, onGuest }: { onComplete: () => void, onSwitchToSignIn: () => void, onGuest: () => void }) => {
  return (
    <div className="h-screen w-full flex items-center justify-center relative overflow-hidden bg-[#0b1326] p-4">
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-violet-600/20 rounded-full blur-[120px]" />
      <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-blue-600/20 rounded-full blur-[120px]" />
      
      <div className="w-full max-w-5xl">
        <GlassCard className="grid grid-cols-1 lg:grid-cols-[1fr_0.9fr]">
          <div className="hidden lg:flex min-h-[520px] flex-col justify-between border-r border-[#494454]/30 bg-[#0b1326]/35 p-8">
            <div>
              <div className="flex items-center gap-2">
                <Sparkles className="text-violet-400" size={20} />
                <span className="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-violet-400 to-blue-400">DataVerse AI</span>
              </div>
              <h2 className="mt-14 text-4xl font-bold tracking-tight text-white leading-tight">Build an analysis workspace in minutes.</h2>
              <p className="mt-5 text-sm text-[#cbc3d7] leading-relaxed max-w-sm">
                Upload data, ask questions, generate visuals, and keep the workflow ready for your next dataset.
              </p>
            </div>
            <div className="grid grid-cols-2 gap-3">
              {['Dataset profiling', 'Natural language analytics', 'Explainable models', 'Exportable reports'].map((item) => (
                <div key={item} className="rounded-xl border border-[#494454]/40 bg-[#171f33]/70 px-4 py-3 text-xs font-medium text-[#cbc3d7]">
                  {item}
                </div>
              ))}
            </div>
          </div>

          <div className="p-6 sm:p-8 lg:p-10">
            <div className="mb-8">
              <h1 className="text-3xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-violet-400 to-blue-400 mb-2">Create workspace</h1>
              <p className="text-[#cbc3d7] text-sm">Start simple. You can continue as a guest anytime.</p>
            </div>

            <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); onComplete(); }}>
              <div>
                <label className="block text-xs font-medium text-[#cbc3d7] mb-1">Full Name</label>
                <input type="text" required autoComplete="name" className="w-full bg-[#0b1326]/50 border border-[#494454] rounded-lg px-4 py-3 text-white text-sm focus:outline-none focus:border-violet-500 transition-colors" />
              </div>
              <div>
                <label className="block text-xs font-medium text-[#cbc3d7] mb-1">Email</label>
                <input type="email" required autoComplete="email" className="w-full bg-[#0b1326]/50 border border-[#494454] rounded-lg px-4 py-3 text-white text-sm focus:outline-none focus:border-violet-500 transition-colors" />
              </div>
              <div>
                <label className="block text-xs font-medium text-[#cbc3d7] mb-1">Password</label>
                <input type="password" required autoComplete="new-password" className="w-full bg-[#0b1326]/50 border border-[#494454] rounded-lg px-4 py-3 text-white text-sm focus:outline-none focus:border-violet-500 transition-colors" />
              </div>
              
              <button type="submit" className="w-full bg-gradient-to-r from-violet-500 to-blue-500 text-white font-medium rounded-lg px-4 py-3 mt-6 hover:brightness-110 active:scale-[0.98] transition-all">
                Initialize Workspace
              </button>
            </form>

            <div className="mt-6 text-center space-y-3">
              <p className="text-sm text-[#cbc3d7]">
                Already have an account?{' '}
                <button type="button" onClick={onSwitchToSignIn} className="text-violet-400 hover:text-violet-300 font-medium">Sign in</button>
              </p>
              <button type="button" onClick={onGuest} className="text-sm text-[#cbc3d7] hover:text-white transition-colors">
                Continue as Guest
              </button>
            </div>
          </div>
        </GlassCard>
      </div>
    </div>
  );
};

const SignInView = ({ onComplete, onSwitchToSignUp, onGuest }: { onComplete: () => void, onSwitchToSignUp: () => void, onGuest: () => void }) => {
  return (
    <div className="h-screen w-full flex items-center justify-center relative overflow-hidden bg-[#0b1326] p-4">
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-violet-600/20 rounded-full blur-[120px]" />
      <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-blue-600/20 rounded-full blur-[120px]" />
      
      <div className="w-full max-w-5xl">
        <GlassCard className="grid grid-cols-1 lg:grid-cols-[0.9fr_1fr]">
          <div className="p-6 sm:p-8 lg:p-10">
            <div className="mb-8">
              <h1 className="text-3xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-violet-400 to-blue-400 mb-2">Welcome back</h1>
              <p className="text-[#cbc3d7] text-sm">Sign in and continue your analysis workspace.</p>
            </div>
            
            <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); onComplete(); }}>
              <div>
                <label className="block text-xs font-medium text-[#cbc3d7] mb-1">Email</label>
                <input type="email" required autoComplete="email" className="w-full bg-[#0b1326]/50 border border-[#494454] rounded-lg px-4 py-3 text-white text-sm focus:outline-none focus:border-violet-500 transition-colors" />
              </div>
              <div>
                <label className="block text-xs font-medium text-[#cbc3d7] mb-1">Password</label>
                <input type="password" required autoComplete="current-password" className="w-full bg-[#0b1326]/50 border border-[#494454] rounded-lg px-4 py-3 text-white text-sm focus:outline-none focus:border-violet-500 transition-colors" />
              </div>
              
              <button type="submit" className="w-full bg-gradient-to-r from-violet-500 to-blue-500 text-white font-medium rounded-lg px-4 py-3 mt-6 hover:brightness-110 active:scale-[0.98] transition-all">
                Sign In
              </button>
            </form>

            <div className="mt-6 text-center space-y-3">
              <p className="text-sm text-[#cbc3d7]">
                Don&apos;t have an account?{' '}
                <button type="button" onClick={onSwitchToSignUp} className="text-violet-400 hover:text-violet-300 font-medium">Sign up</button>
              </p>
              <button type="button" onClick={onGuest} className="text-sm text-[#cbc3d7] hover:text-white transition-colors">
                Continue as Guest
              </button>
            </div>
          </div>

          <div className="hidden lg:flex min-h-[480px] flex-col justify-between border-l border-[#494454]/30 bg-[#0b1326]/35 p-8">
            <div>
              <div className="flex items-center gap-2">
                <Sparkles className="text-violet-400" size={20} />
                <span className="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-violet-400 to-blue-400">DataVerse AI</span>
              </div>
              <h2 className="mt-14 text-4xl font-bold tracking-tight text-white leading-tight">Return to your active analysis.</h2>
              <p className="mt-5 text-sm text-[#cbc3d7] leading-relaxed max-w-sm">
                Continue from uploaded datasets, previous questions, generated charts, and model explanations.
              </p>
            </div>
            <div className="rounded-2xl border border-[#494454]/40 bg-[#171f33]/70 p-5">
              <div className="flex items-center gap-3 text-sm font-medium text-white">
                <CheckCircle2 size={17} className="text-emerald-400" />
                Workspace sync ready
              </div>
              <p className="mt-3 text-xs leading-relaxed text-[#cbc3d7]">
                Sign in to keep reports, datasets, and generated insights organized in one place.
              </p>
            </div>
          </div>
        </GlassCard>
      </div>
    </div>
  );
};


const HomeView = ({
  dataset,
  uploadStatus,
  onUpload,
  onSubmit,
}: {
  dataset: DatasetSummary | null;
  uploadStatus: string | null;
  onUpload: (file: File) => void;
  onSubmit: (query: string) => void;
}) => {
  return (
    <div className="flex-1 w-full h-full flex flex-col relative overflow-hidden items-center justify-center">
      {/* Background elements */}
      <div className="absolute top-1/4 left-1/4 w-[400px] h-[400px] md:w-[600px] md:h-[600px] bg-violet-600/15 rounded-full blur-[100px] md:blur-[120px] pointer-events-none" />
      <div className="absolute bottom-1/4 right-1/4 w-[400px] h-[400px] md:w-[600px] md:h-[600px] bg-blue-600/15 rounded-full blur-[100px] md:blur-[120px] pointer-events-none" />

      {/* Main Center Content */}
      <motion.div 
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-[800px] px-4 md:px-8 text-center z-10 flex flex-col items-center justify-center -mt-20 md:-mt-10"
      >
        <h2 className="text-3xl md:text-5xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-white to-[#cbc3d7] tracking-tight mb-8">
          What shall we analyze today?
        </h2>
        <GlassCard className="w-full p-4 md:p-5 text-left border-[#494454]/50">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="flex items-start gap-3">
              <div className="w-10 h-10 rounded-lg bg-[#2d3449] flex items-center justify-center border border-[#494454]/50 text-violet-400 shrink-0">
                {dataset ? <Table size={20} /> : <CloudUpload size={20} />}
              </div>
              <div>
                <h3 className="text-sm font-semibold text-white">
                  {dataset?.dataset_filename || 'Upload a CSV or Excel file'}
                </h3>
                <p className="text-xs text-[#cbc3d7] mt-1">
                  {uploadStatus || (dataset ? `${formatNumber(dataset.dataset_rows)} rows, ${formatNumber(dataset.dataset_cols)} columns connected to ${API_BASE_URL}` : `Backend target: ${API_BASE_URL}`)}
                </p>
                {dataset && (
                  <p className="text-[11px] text-blue-300 mt-1">Detected type: {datasetTypeLabel(dataset)}</p>
                )}
              </div>
            </div>
            {dataset && (
              <span className="px-3 py-1 bg-emerald-500/10 border border-emerald-500/30 rounded text-xs text-emerald-300 flex items-center gap-2 font-medium self-start md:self-auto">
                <CheckCircle2 size={14} /> Ready
              </span>
            )}
          </div>
        </GlassCard>
      </motion.div>
      
      <FloatingInput
        onSubmit={onSubmit}
        onFileUpload={onUpload}
        disabled={uploadStatus?.toLowerCase().includes('uploading') ?? false}
        placeholder={dataset ? 'Ask about your uploaded dataset...' : 'Attach a dataset, then ask a question...'}
      />
    </div>
  );
};


const ChatView = ({
  dataset,
  messages,
  isQuerying,
  onUpload,
  onSubmit,
}: {
  dataset: DatasetSummary | null;
  messages: ChatMessage[];
  isQuerying: boolean;
  onUpload: (file: File) => void;
  onSubmit: (query: string) => void;
}) => {
  const [showPanel, setShowPanel] = useState(true);
  const latestAssistant = [...messages].reverse().find((message) => message.role === 'assistant');
  const latestEvents = latestAssistant?.events ?? [];

  return (
    <div className="flex-1 w-full h-full flex flex-col relative overflow-hidden">
      <div className="flex-1 overflow-y-auto w-full px-4 md:px-8 scroll-smooth">
        <div className="max-w-[800px] mx-auto pt-24 flex flex-col pb-48 space-y-8">
          {!dataset && (
            <GlassCard className="p-5 border-amber-500/20">
              <div className="flex items-start gap-3">
                <AlertTriangle className="text-amber-400 shrink-0 mt-0.5" size={18} />
                <div>
                  <h3 className="text-sm font-semibold text-white">Dataset needed</h3>
                  <p className="text-sm text-[#cbc3d7] mt-1">Use the paperclip button to upload a CSV or Excel file before sending analysis questions.</p>
                </div>
              </div>
            </GlassCard>
          )}

          {dataset && (
            <GlassCard className="p-4 border-[#494454]/50">
              <div className="flex items-center justify-between gap-4">
                <div className="flex items-center gap-3 min-w-0">
                  <Table size={18} className="text-violet-400 shrink-0" />
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-white truncate">{dataset.dataset_filename}</p>
                    <p className="text-xs text-[#cbc3d7]">{formatNumber(dataset.dataset_rows)} rows, {formatNumber(dataset.dataset_cols)} columns ├óÔé¼┬ó {datasetTypeLabel(dataset)}</p>
                  </div>
                </div>
                <span className="text-xs text-emerald-300 bg-emerald-500/10 border border-emerald-500/30 px-2.5 py-1 rounded">Connected</span>
              </div>
            </GlassCard>
          )}

          {messages.map((message) => (
            <motion.div
              key={message.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className={`flex gap-4 ${message.role === 'user' ? 'self-end max-w-[85%]' : 'self-start max-w-[90%] md:max-w-[85%]'}`}
            >
              {message.role !== 'user' && (
                <div className={`w-8 h-8 rounded-full bg-gradient-to-br from-violet-500 to-blue-500 shrink-0 mt-1 flex items-center justify-center shadow-md ${message.isLoading ? 'animate-pulse' : ''}`}>
                  {BOT_AVATAR}
                </div>
              )}
              <div className="flex-1 space-y-3 min-w-0">
                <div className={`${message.role === 'user' ? 'bg-[#222a3d] rounded-tr-sm' : 'bg-[#171f33]/70 rounded-tl-sm'} text-white px-5 py-4 rounded-2xl shadow-sm border border-[#494454]/30`}>
                  <p className="text-sm leading-relaxed whitespace-pre-wrap">{message.content}</p>
                </div>

                {message.role === 'assistant' && message.events?.length ? (
                  <div className="bg-[#171f33]/50 border border-[#494454]/50 rounded-xl overflow-hidden backdrop-blur-md">
                    <button onClick={() => setShowPanel(!showPanel)} className="w-full flex items-center justify-between px-4 py-3 hover:bg-white/5 transition-colors">
                      <div className="flex items-center gap-3">
                        {message.isLoading ? (
                          <div className="w-4 h-4 border-2 border-violet-400 border-t-transparent rounded-full animate-spin"></div>
                        ) : (
                          <CheckCircle2 size={16} className="text-emerald-400" />
                        )}
                        <span className={`text-sm ${message.isLoading ? 'text-violet-400 opacity-80 animate-pulse' : 'text-emerald-400'}`}>
                          {message.isLoading ? 'Analyzing dataset...' : 'Analysis complete'}
                        </span>
                      </div>
                      <ArrowUp size={16} className={`text-[#cbc3d7] transition-transform duration-300 ${showPanel ? 'rotate-180' : ''}`} />
                    </button>

                    <AnimatePresence>
                      {showPanel && (
                        <motion.div
                          initial={{ height: 0, opacity: 0 }}
                          animate={{ height: 'auto', opacity: 1 }}
                          exit={{ height: 0, opacity: 0 }}
                          className="overflow-hidden border-t border-[#494454]/30"
                        >
                          <div className="px-4 pb-4 pt-3 space-y-3 bg-[#0b1326]/40">
                            {message.events.map((event, index) => (
                              <div className="flex items-center gap-3" key={`${message.id}-${event.step}-${index}`}>
                                {event.step === 'error' ? <AlertTriangle size={16} className="text-amber-400" /> : <CheckCircle2 size={16} className="text-blue-400" />}
                                <span className="font-mono text-xs text-[#cbc3d7]">{event.message}</span>
                              </div>
                            ))}
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                ) : null}

                {message.tables?.map((table) => (
                  <ResultTable key={`${message.id}-${table.title}`} table={table} />
                ))}

                {message.charts?.map((chart) => (
                  <SimpleChart key={`${message.id}-${chart.title}`} chart={chart} />
                ))}

                {message.recommendations?.length ? (
                  <GlassCard className="p-4 border-emerald-500/20">
                    <div className="flex items-center gap-3 mb-3">
                      <Target size={16} className="text-emerald-300" />
                      <span className="text-sm font-medium text-white">Recommendations</span>
                    </div>
                    <ul className="space-y-2">
                      {message.recommendations.map((recommendation) => (
                        <li key={recommendation} className="text-xs text-[#cbc3d7] leading-relaxed">{recommendation}</li>
                      ))}
                    </ul>
                  </GlassCard>
                ) : null}

                {message.report?.pdf_url || message.report?.html_url ? (
                  <GlassCard className="p-4 border-blue-500/20">
                    <div className="flex items-center gap-3 mb-3">
                      <FileText size={16} className="text-blue-300" />
                      <span className="text-sm font-medium text-white">Final Report</span>
                    </div>
                    <div className="flex flex-col sm:flex-row gap-3">
                      {message.report?.pdf_url && (
                        <a
                          href={message.report.pdf_url}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center justify-center gap-2 bg-gradient-to-r from-violet-500 to-blue-500 text-white px-4 py-2 rounded-lg text-xs font-medium hover:brightness-110 transition-all"
                        >
                          <FileText size={14} /> Download PDF Report
                        </a>
                      )}
                      {message.report?.html_url && (
                        <a
                          href={message.report.html_url}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center justify-center gap-2 bg-[#222a3d] border border-[#494454] text-white px-4 py-2 rounded-lg text-xs font-medium hover:bg-white/5 transition-all"
                        >
                          <FileText size={14} /> Download HTML Report
                        </a>
                      )}
                    </div>
                  </GlassCard>
                ) : null}

                {message.suggestions?.length ? (
                  <div className="flex flex-wrap gap-2">
                    {message.suggestions.map((suggestion) => (
                      <button
                        key={suggestion}
                        type="button"
                        onClick={() => onSubmit(suggestion)}
                        className="text-xs text-violet-200 bg-violet-500/10 border border-violet-500/30 rounded-full px-3 py-1 hover:bg-violet-500/20 transition-colors"
                      >
                        {suggestion}
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
              {message.role === 'user' && (
                <div className="w-8 h-8 rounded-full overflow-hidden shrink-0 mt-1 border border-[#494454]">
                  <img src={USER_AVATAR} alt="User avatar" className="w-full h-full object-cover" />
                </div>
              )}
            </motion.div>
          ))}

          {isQuerying && !latestEvents.length && (
            <div className="flex gap-4 self-start w-full opacity-50 mt-4">
              <div className="h-20 w-[400px] max-w-full bg-[#171f33] rounded-2xl animate-pulse delay-150"></div>
            </div>
          )}
        </div>
      </div>
      <FloatingInput
        onSubmit={onSubmit}
        onFileUpload={onUpload}
        disabled={isQuerying}
        placeholder={dataset ? 'Ask another question...' : 'Upload a dataset first...'}
      />
    </div>
  );
};

const DataHubView = ({
  dataset,
  messages,
  onUpload,
  onSubmit,
}: {
  dataset: DatasetSummary | null;
  messages: ChatMessage[];
  onUpload: (file: File) => void;
  onSubmit: (query: string) => void;
}) => {
  const assistantMessages = messages.filter((message) => message.role === 'assistant');
  const latestAssistant = assistantMessages.at(-1);
  const latestNarrative = latestAssistant?.content || 'Upload a dataset and run an analysis to populate this workspace with live backend results.';
  const schemaPreview = dataset?.column_names?.slice(0, 6) ?? [];
  const dtypeMap = new Map((dataset?.column_names ?? []).map((column, index) => [column, dataset?.column_dtypes?.[index]]));
  const numericColumns = (dataset?.column_names ?? []).filter((column) => isNumericType(dtypeMap.get(column)));
  const categoricalColumns = (dataset?.column_names ?? []).filter((column) => !isNumericType(dtypeMap.get(column)));
  const profile = dataset?.dataset_profile as Record<string, unknown> | undefined;
  const quality = (profile?.quality ?? {}) as Record<string, unknown>;
  const previewRows = dataset?.dataset_preview ?? [];
  const previewColumns = previewRows.length ? Object.keys(previewRows[0]).slice(0, 6) : [];
  const semanticColumns = Object.entries((profile?.semantic_columns ?? {}) as Record<string, unknown>).filter(([, column]) => Boolean(column));
  const suggestedQuestions = datasetSuggestions(dataset);

  return (
    <div className="flex-1 w-full mx-auto px-4 md:px-8 pb-32 pt-24 overflow-y-auto overflow-x-hidden">
      <div className="max-w-[1000px] mx-auto space-y-8">
        
        {/* Header Block */}
        <div className="flex items-center gap-3">
           <div className="w-10 h-10 rounded-full bg-gradient-to-br from-violet-500 to-blue-500 flex items-center justify-center shadow-lg">
             <Bot size={20} className="text-white" />
           </div>
           <div>
             <h1 className="text-xl md:text-2xl font-semibold text-white">{dataset?.dataset_filename ? 'Dataset Workspace' : 'DataVerse Workspace'}</h1>
             <p className="text-sm text-[#cbc3d7]">{dataset?.dataset_filename || 'No dataset uploaded yet'}</p>
           </div>
        </div>

        {!dataset && (
          <GlassCard className="p-6 border-amber-500/20">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div className="flex items-start gap-3">
                <CloudUpload size={20} className="text-amber-400 shrink-0 mt-0.5" />
                <div>
                  <h2 className="text-base font-semibold text-white">Connect your backend data flow</h2>
                  <p className="text-sm text-[#cbc3d7] mt-1">Upload a CSV or Excel file. The frontend will send it to <span className="font-mono text-violet-300">{API_BASE_URL}/api/upload</span>.</p>
                </div>
              </div>
              <label className="bg-gradient-to-r from-violet-500 to-blue-500 text-white px-4 py-2.5 rounded-lg text-sm font-medium hover:brightness-110 active:scale-95 transition-all cursor-pointer text-center">
                Upload Dataset
                <input type="file" accept=".csv,.xlsx,.xls" className="hidden" onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) onUpload(file);
                  event.target.value = '';
                }} />
              </label>
            </div>
          </GlassCard>
        )}

        {/* Top Section: Dataset Summary */}
        <GlassCard className="p-6 relative group border-[#494454]/50">
          <div className="absolute -top-12 -right-12 w-48 h-48 bg-violet-500/10 rounded-full blur-[60px] group-hover:bg-violet-500/20 transition-all duration-700"></div>
          
          <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-8 relative z-10">
            <div className="flex-1">
              <div className="flex items-center gap-3 mb-2">
                <div className="w-10 h-10 rounded-lg bg-[#2d3449] flex items-center justify-center border border-[#494454]/50 text-violet-400">
                  <Table size={20} />
                </div>
                <div>
                  <h2 className="text-lg font-semibold text-white">{dataset?.dataset_filename || 'Waiting for dataset'}</h2>
                  <p className="text-xs text-[#cbc3d7] mt-1">{dataset ? `${dataset.message} | ${datasetTypeLabel(dataset)} | Ready for analysis` : 'Upload from the chat bar or dashboard prompt'}</p>
                </div>
              </div>

              <div className="flex items-center gap-6 mt-6 border-t border-[#494454]/30 pt-5">
                <div>
                  <p className="text-[10px] text-[#cbc3d7] mb-1 uppercase tracking-wider font-semibold">Rows</p>
                  <p className="text-lg font-medium text-white">{formatNumber(dataset?.dataset_rows)}</p>
                </div>
                <div className="w-px h-8 bg-[#494454]/50"></div>
                <div>
                  <p className="text-[10px] text-[#cbc3d7] mb-1 uppercase tracking-wider font-semibold">Columns</p>
                  <p className="text-lg font-medium text-white">{formatNumber(dataset?.dataset_cols)}</p>
                </div>
                <div className="w-px h-8 bg-[#494454]/50"></div>
                <div>
                  <p className="text-[10px] text-[#cbc3d7] mb-1 uppercase tracking-wider font-semibold">File Size</p>
                  <div className="flex items-center gap-1.5 text-blue-400">
                    <CheckCircle2 size={16} />
                    <p className="text-lg font-medium text-white">{formatFileSize(dataset?.originalFileSize)}</p>
                  </div>
                </div>
                <div className="w-px h-8 bg-[#494454]/50"></div>
                <div>
                  <p className="text-[10px] text-[#cbc3d7] mb-1 uppercase tracking-wider font-semibold">Dataset Type</p>
                  <p className="text-lg font-medium text-white">{dataset ? datasetTypeLabel(dataset) : 'Generic'}</p>
                </div>
              </div>
            </div>

            <div className="w-full lg:w-auto bg-[#0b1326]/50 rounded-xl p-5 border border-[#494454]/30 min-w-[300px]">
              <p className="text-xs text-[#cbc3d7] mb-4 flex items-center gap-2 font-medium tracking-wide uppercase">
                <Layers size={14} /> Detected Schema
              </p>
              <div className="flex flex-wrap gap-2">
                {schemaPreview.length ? schemaPreview.map((column) => {
                  const dtype = dtypeMap.get(column);
                  const numeric = isNumericType(dtype);
                  const Icon = numeric ? Hash : dtype?.toLowerCase().includes('date') ? Calendar : List;
                  return (
                    <div key={column} className={`flex items-center gap-1.5 bg-[#171f33] px-2.5 py-1.5 rounded ${numeric ? 'text-blue-300' : 'text-amber-300'} font-mono text-xs border border-[#494454]`}>
                      <Icon size={12} /> {column}
                    </div>
                  );
                }) : (
                  <div className="flex items-center gap-1.5 bg-[#171f33] px-2.5 py-1.5 rounded text-[#cbc3d7] font-mono text-xs border border-[#494454]">
                    No schema loaded
                  </div>
                )}
                {(dataset?.column_names?.length ?? 0) > schemaPreview.length && (
                  <div className="flex items-center gap-1.5 bg-[#171f33] px-2.5 py-1.5 rounded text-[#cbc3d7] font-mono text-xs border border-[#494454] border-dashed">
                    + {(dataset?.column_names?.length ?? 0) - schemaPreview.length} more
                  </div>
                )}
              </div>
            </div>
          </div>
        </GlassCard>

        {dataset && (
          <div className="grid grid-cols-1 xl:grid-cols-[0.8fr_1.2fr] gap-6">
            <GlassCard className="p-5 border-emerald-500/20">
              <div className="flex items-center justify-between gap-4 mb-5">
                <div>
                  <h2 className="text-base font-semibold text-white">Data Quality</h2>
                  <p className="text-xs text-[#cbc3d7] mt-1">Calculated during upload</p>
                </div>
                <div className="text-2xl font-semibold text-emerald-300">{formatCell(quality.score ?? 0)}</div>
              </div>
              <div className="grid grid-cols-2 gap-3 text-xs">
                <div className="bg-[#131b2e] rounded p-3 border border-[#494454]/40">
                  <p className="text-[#cbc3d7]">Missing cells</p>
                  <p className="text-white font-medium mt-1">{formatCell(quality.total_missing ?? 0)}</p>
                </div>
                <div className="bg-[#131b2e] rounded p-3 border border-[#494454]/40">
                  <p className="text-[#cbc3d7]">Duplicate rows</p>
                  <p className="text-white font-medium mt-1">{formatCell(quality.duplicate_rows ?? 0)}</p>
                </div>
              </div>
              <div className="mt-5">
                <p className="text-[10px] text-[#cbc3d7] uppercase tracking-wider font-semibold mb-2">Business column mapping</p>
                <div className="flex flex-wrap gap-2">
                  {semanticColumns.length ? semanticColumns.map(([role, column]) => (
                    <span key={role} className="text-[11px] bg-emerald-500/10 text-emerald-200 border border-emerald-500/20 rounded px-2 py-1">
                      {role}: {String(column)}
                    </span>
                  )) : (
                    <span className="text-xs text-[#cbc3d7]">No business roles detected yet.</span>
                  )}
                </div>
              </div>
            </GlassCard>

            <GlassCard className="overflow-hidden border-blue-500/20">
              <div className="flex items-center gap-3 px-5 py-4 border-b border-[#494454]/40">
                <FileSpreadsheet size={16} className="text-blue-300" />
                <span className="text-sm font-medium text-white">Dataset Preview</span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-[#131b2e] text-[#cbc3d7]">
                    <tr>
                      {previewColumns.map((column) => <th key={column} className="px-4 py-3 font-semibold whitespace-nowrap">{column}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {previewRows.slice(0, 5).map((row, index) => (
                      <tr key={index} className="border-t border-[#494454]/30 text-slate-100">
                        {previewColumns.map((column) => <td key={column} className="px-4 py-3 whitespace-nowrap">{formatCell(row[column])}</td>)}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </GlassCard>
          </div>
        )}

        {/* Model Status & Explanations side-by-side on desktop */}
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 mt-6">
           {/* Model Status Panel */}
           <GlassCard className="p-6 flex flex-col gap-6">
              <div className="flex justify-between items-start">
                  <div>
                      <h2 className="text-lg font-semibold text-white">Model Status</h2>
                      <p className="text-sm text-[#cbc3d7] mt-1">{dataset ? 'Backend session initialized' : 'Awaiting upload'}</p>
                  </div>
                  <span className="px-3 py-1 bg-[#222a3d] border border-[#494454] rounded text-xs text-blue-400 flex items-center gap-2 font-medium">
                      <span className="w-2 h-2 rounded-full bg-blue-400 animate-pulse"></span>
                      {dataset ? datasetTypeLabel(dataset) : 'Generic'}
                  </span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="bg-[#131b2e] rounded-lg p-5 border border-[#494454]/50">
                      <div className="text-xs text-[#cbc3d7] mb-2 font-medium">Numeric Columns</div>
                      <div className="text-3xl font-bold text-violet-400 tracking-tight">{numericColumns.length}</div>
                      <div className="text-[11px] text-emerald-400 flex items-center gap-1 mt-2 font-medium">
                          <TrendingUp size={12} /> Available for stats and charts
                      </div>
                  </div>
                  <div className="bg-[#131b2e] rounded-lg p-5 border border-[#494454]/50">
                      <div className="text-xs text-[#cbc3d7] mb-2 font-medium">Category Columns</div>
                      <div className="text-3xl font-bold text-blue-400 tracking-tight">{categoricalColumns.length}</div>
                      <div className="text-[11px] text-[#cbc3d7] mt-2 font-medium">Available for grouping</div>
                  </div>
                  <div className="bg-[#131b2e] rounded-lg p-5 border border-[#494454]/50 col-span-1 sm:col-span-2">
                       <div className="flex justify-between items-center mb-3">
                           <span className="text-xs text-[#cbc3d7] font-medium">Backend Connection</span>
                           <span className="text-xs text-violet-400 font-mono">{dataset ? 'online' : 'waiting'}</span>
                       </div>
                       <div className="w-full bg-[#222a3d] rounded-full h-1.5 mb-3">
                           <div className="bg-gradient-to-r from-violet-500 to-blue-500 h-1.5 rounded-full" style={{ width: dataset ? '100%' : '35%' }}></div>
                       </div>
                       <div className="text-[11px] text-emerald-400 flex items-center gap-1 font-medium">
                           <CheckCircle2 size={12} /> {dataset ? `Session ${dataset.session_id.slice(0, 8)} ready` : 'Upload to create a backend session'}
                       </div>
                  </div>
              </div>
           </GlassCard>

           {/* XAI Explainability Panel */}
           <div className="flex gap-4 items-start w-full">
              <div className="w-10 h-10 rounded-full bg-gradient-to-br from-violet-500 to-blue-500 flex-shrink-0 flex items-center justify-center shadow-lg mt-1 hidden sm:flex">
                  <BrainCircuit size={18} className="text-white" />
              </div>
              <div className="flex-1 bg-[#171f33]/80 backdrop-blur-xl rounded-2xl sm:rounded-tl-sm p-1 border border-[#494454]/50 shadow-[0_8px_32px_rgba(109,59,215,0.08)]">
                  <div className="bg-[#0b1326]/60 rounded-xl p-5 sm:p-6 h-full flex flex-col">
                      <p className="text-sm text-white/90 mb-6 leading-relaxed">{latestNarrative}</p>
                      
                      <div className="border-b border-[#494454]/50 mb-6 flex gap-6">
                           <button className="border-b-2 border-violet-400 py-2 text-xs font-semibold text-violet-400">Global Feature Importance</button>
                           <button className="border-b-2 border-transparent py-2 text-xs font-semibold text-[#cbc3d7] hover:text-white transition-colors">Local (LIME)</button>
                      </div>

                      <div className="space-y-5 flex-1">
                          {(numericColumns.length ? numericColumns : ['Upload a numeric column']).slice(0, 4).map((name, index) => ({ name, score: Math.max(0.05, 0.24 - index * 0.045), w: `${Math.max(25, 100 - index * 20)}%` })).map((feat) => (
                             <div key={feat.name} className="flex items-center gap-4">
                                <div className="w-32 sm:w-40 text-[11px] font-mono text-right truncate text-white border-r border-[#494454]/50 pr-4">{feat.name}</div>
                                <div className="flex-1 flex items-center group">
                                   <div className="h-2.5 bg-violet-500/80 rounded-r-sm group-hover:bg-violet-400 transition-colors" style={{ width: feat.w }}></div>
                                </div>
                                <div className="w-12 text-[11px] text-[#cbc3d7] font-mono text-right">{feat.score.toFixed(3)}</div>
                             </div>
                          ))}
                      </div>
                  </div>
              </div>
           </div>
        </div>

        {/* Relevant Follow-up Questions */}
        <section className="mt-8 pt-4">
          <div className="flex items-center gap-3 mb-6 px-1">
            <div className="w-2 h-2 rounded-full bg-violet-400 animate-pulse"></div>
            <h3 className="text-lg font-semibold text-white flex items-center gap-3">
              Relevant Follow-ups
              <span className="text-[10px] bg-[#222a3d] text-violet-300 px-2 py-0.5 rounded border border-violet-500/20 uppercase tracking-wider font-bold">{dataset ? datasetTypeLabel(dataset) : 'Generic'}</span>
            </h3>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {suggestedQuestions.map((question, index) => {
              const Icon = index % 3 === 0 ? Target : index % 3 === 1 ? BarChart2 : MessageSquare;
              return (
                <button key={question} type="button" onClick={() => onSubmit(question)} className="text-left">
                  <GlassCard className="p-5 flex flex-col relative overflow-hidden group h-full">
                    <div className="flex items-start gap-3">
                      <div className="w-8 h-8 rounded-lg bg-blue-500/10 flex items-center justify-center text-blue-400 border border-blue-500/20 shrink-0">
                        <Icon size={16} />
                      </div>
                      <p className="text-sm text-white leading-relaxed">{question}</p>
                    </div>
                  </GlassCard>
                </button>
              );
            })}
          </div>
        </section>
      </div>
    </div>
  );
};


// --- App Layout Shell ---

export default function App() {
  const [currentView, setCurrentView] = useState<ViewState>('landing');
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
  const [recentDatasets, setRecentDatasets] = useState<RecentDataset[]>([]);
  const [dataset, setDataset] = useState<DatasetSummary | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isQuerying, setIsQuerying] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<string | null>(null);

  const refreshSidebar = async () => {
    try {
      const [nextSessions, nextDatasets] = await Promise.all([listSessions(), listDatasets()]);
      setSessions(nextSessions);
      setRecentDatasets(nextDatasets);
    } catch {
      // Local development can start before the backend. Keep a clean new chat screen.
    }
  };

  useEffect(() => {
    let cancelled = false;
    Promise.all([listSessions(), listDatasets()])
      .then(([nextSessions, nextDatasets]) => {
        if (!cancelled) {
          setSessions(nextSessions);
          setRecentDatasets(nextDatasets);
        }
      })
      .catch(() => {
        // Backend may not be running yet; keep a clean empty chat.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleNewChat = async () => {
    setDataset(null);
    setMessages([]);
    setUploadStatus(null);
    setIsQuerying(false);
    setCurrentView('home');
    try {
      const session = await createSession();
      setCurrentSessionId(session.id);
      await refreshSidebar();
    } catch {
      setCurrentSessionId(null);
    }
  };

  const loadSession = async (sessionId: string) => {
    const detail = await getSession(sessionId);
    setCurrentSessionId(detail.id);
    const active = detail.datasets.find((item) => item.id === detail.active_dataset_id) ?? detail.datasets[0];
    setDataset(active ? datasetFromRecent(active) : null);
    setMessages(detail.messages.filter((item): item is typeof item & { role: ChatRole } => item.role !== 'agent').map((item) => ({
      id: item.id,
      role: item.role,
      content: item.content,
      events: Array.isArray(item.payload?.agents)
        ? (item.payload.agents as Array<{ name: string; status: string; summary?: string }>).map((agent) => ({
          step: agent.name,
          message: `${agent.name}: ${agent.status}${agent.summary ? ` - ${agent.summary}` : ''}`,
        }))
        : undefined,
      charts: item.payload?.charts as ChartPayload[] | undefined,
      tables: item.payload?.tables as TablePayload[] | undefined,
      recommendations: item.payload?.recommendations as string[] | undefined,
      report: item.payload?.report as ChatMessage['report'],
    })));
    setCurrentView('chat');
    await refreshSidebar();
  };

  const handleUpload = async (file: File) => {
    setUploadStatus(`Uploading ${file.name}...`);
    try {
      const sessionId = currentSessionId || (await createSession()).id;
      setCurrentSessionId(sessionId);
      const uploaded = await uploadDataset(file, sessionId, { autoAnalyze: true, generateReport: true, runXai: true });
      const nextDataset = { ...uploaded, originalFileSize: file.size };
      setDataset(nextDataset);
      setUploadStatus(uploaded.analysis ? `${file.name} uploaded and analyzed.` : `${file.name} uploaded successfully.`);
      const systemMessage: ChatMessage = {
        id: crypto.randomUUID(),
        role: 'system',
        content: `${uploaded.dataset_filename || file.name} is ready: ${formatNumber(uploaded.dataset_rows)} rows, ${formatNumber(uploaded.dataset_cols)} columns, ${datasetTypeLabel(nextDataset)} dataset type.`,
      };
      const analysisMessage: ChatMessage | null = uploaded.analysis
        ? {
            id: crypto.randomUUID(),
            role: 'assistant',
            content: uploaded.analysis.answer || 'Analysis complete.',
            events: uploaded.analysis.agents.flatMap((agent) => [
              { step: agent.name, message: `${agent.name}: ${agent.status}${agent.summary ? ` - ${agent.summary}` : ''}` },
              ...(agent.steps ?? []).map((step) => ({
                step: agent.name,
                message: `${agent.name} / ${step.name}: ${step.status}`,
              })),
            ]),
            tables: uploaded.analysis.tables,
            charts: uploaded.analysis.charts,
            recommendations: uploaded.analysis.recommendations,
            report: uploaded.analysis.report,
          }
        : null;
      setMessages((current) => [
        ...current,
        systemMessage,
        ...(analysisMessage ? [analysisMessage] : []),
      ]);
      await refreshSidebar();
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Upload failed';
      setUploadStatus(message);
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: `Upload failed: ${message}`,
        },
      ]);
    }
  };

  const runAnalysis = async (sessionId: string, datasetId: string, query: string) => {
    const assistantId = crypto.randomUUID();
    setCurrentView('chat');
    setIsQuerying(true);
    setMessages((current) => [
      ...current,
      { id: crypto.randomUUID(), role: 'user', content: query },
      {
        id: assistantId,
        role: 'assistant',
        content: 'AnalysisAgent is profiling the dataset...',
        events: [
          { step: 'AnalysisAgent', message: 'AnalysisAgent: running - profiling dataset, semantic mapping, EDA, trends, and business metrics' },
        ],
        isLoading: true,
      },
    ]);
    try {
      const result = await analyzeSession(sessionId, datasetId, query);
      setMessages((current) => current.map((message) => (
        message.id === assistantId
          ? {
              ...message,
              content: result.answer || 'Analysis complete.',
              events: (result.agents ?? []).flatMap((agent) => [
                { step: agent.name, message: `${agent.name}: ${agent.status}${agent.summary ? ` - ${agent.summary}` : ''}` },
                ...(agent.steps ?? []).map((step) => ({
                  step: agent.name,
                  message: `${agent.name} / ${step.name}: ${step.status}`,
                })),
              ]),
              tables: result.tables,
              charts: result.charts,
              recommendations: result.recommendations,
              report: result.report,
              isLoading: false,
            }
          : message
      )));
      await refreshSidebar();
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Analysis failed';
      setMessages((current) => current.map((item) => (
        item.id === assistantId
          ? { ...item, content: `Analysis failed: ${message}`, events: [{ step: 'error', message }], isLoading: false }
          : item
      )));
    } finally {
      setIsQuerying(false);
    }
  };

  const handleSubmit = async (query: string) => {
    if (!dataset || !currentSessionId) {
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: 'Please upload a CSV or Excel dataset first, then I can analyze it through the backend.',
        },
      ]);
      setCurrentView('chat');
      return;
    }

    const assistantId = crypto.randomUUID();
    setCurrentView('chat');
    setIsQuerying(true);
    setMessages((current) => [
      ...current,
      { id: crypto.randomUUID(), role: 'user', content: query },
      {
        id: assistantId,
        role: 'assistant',
        content: 'Running backend analysis...',
        events: [],
        isLoading: true,
      },
    ]);

    try {
      const events = await streamQuery(currentSessionId, query, (event) => {
        setMessages((current) => current.map((message) => {
          if (message.id !== assistantId) {
            return message;
          }

          const nextTables = event.table
            ? [...(message.tables ?? []), event.table]
            : message.tables;
          const nextCharts = event.chart
            ? [...(message.charts ?? []), event.chart]
            : message.charts;
          const nextRecommendations = event.recommendations ?? message.recommendations;

          return {
            ...message,
            content: event.step === 'narration' || event.step === 'error' ? event.message : message.content,
            events: [...(message.events ?? []), event],
            tables: nextTables,
            charts: nextCharts,
            recommendations: nextRecommendations,
            suggestions: event.suggestions ?? message.suggestions,
          };
        }));
      });

      const narrative = [...events].reverse().find((event) => event.step === 'narration')?.message;
      setMessages((current) => current.map((message) => (
        message.id === assistantId
          ? { ...message, content: narrative || message.content || 'Analysis complete.', isLoading: false }
          : message
      )));
      const detail = await getSession(currentSessionId);
      const lastAssistant = [...detail.messages].reverse().find((item) => item.role === 'assistant');
      if (lastAssistant?.payload?.report) {
        setMessages((current) => current.map((message) => (
          message.id === assistantId
            ? {
                ...message,
                report: lastAssistant.payload?.report as ChatMessage['report'],
                charts: lastAssistant.payload?.charts as ChartPayload[] | undefined,
                tables: lastAssistant.payload?.tables as TablePayload[] | undefined,
                recommendations: lastAssistant.payload?.recommendations as string[] | undefined,
              }
            : message
        )));
      }
      await refreshSidebar();
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Analysis failed';
      setMessages((current) => current.map((item) => (
        item.id === assistantId
          ? { ...item, content: `Analysis failed: ${message}`, isLoading: false }
          : item
      )));
    } finally {
      setIsQuerying(false);
    }
  };

  // Handle fake auth
  if (currentView === 'landing') {
    return <LandingView onNavigate={setCurrentView} />;
  }

  if (currentView === 'signup') {
    return <SignUpView onComplete={handleNewChat} onSwitchToSignIn={() => setCurrentView('signin')} onGuest={handleNewChat} />;
  }
  
  if (currentView === 'signin') {
    return <SignInView onComplete={handleNewChat} onSwitchToSignUp={() => setCurrentView('signup')} onGuest={handleNewChat} />;
  }

  return (
    <div className="flex h-screen w-full bg-[#0b1326] text-white font-sans overflow-hidden">
      
      {/* --- Desktop Sidebar --- */}
      <aside className="hidden md:flex bg-[#171f33] w-[280px] h-full rounded-r-2xl border-r border-[#494454]/30 shadow-2xl flex-col py-6 shrink-0 z-40">
        <div className="px-6 mb-6 mt-2">
          <div className="flex items-center gap-4">
            <div className="w-10 h-10 rounded-full border-2 border-violet-500/30 overflow-hidden shadow-inner">
              <img src={USER_AVATAR} alt="User" className="w-full h-full object-cover" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-white tracking-wide">DataVerse Workspace</h2>
              <div className="flex items-center gap-2 mt-0.5">
                <span className="text-[10px] font-medium text-[#cbc3d7] bg-[#2d3449] px-2 py-0.5 rounded-full">{currentSessionId ? `Session ${currentSessionId.slice(0, 8)}` : 'Clean New Chat'}</span>
              </div>
            </div>
          </div>
        </div>
        
        <nav className="flex-1 overflow-y-auto space-y-6 px-3 pb-4">
          
          <div className="space-y-1">
            <button onClick={handleNewChat} className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-xl transition-all duration-200 ${currentView === 'home' && !dataset ? 'bg-violet-500/15 text-violet-300 font-medium' : 'text-[#cbc3d7] hover:bg-white/5 hover:text-white'}`}>
              <Sparkles size={18} />
              <span className="text-sm">New Chat</span>
            </button>
            <button onClick={() => setCurrentView('chat')} className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-xl transition-all duration-200 ${currentView === 'chat' ? 'bg-violet-500/15 text-violet-300 font-medium' : 'text-[#cbc3d7] hover:bg-white/5 hover:text-white'}`}>
              <History size={18} />
              <span className="text-sm">Active Run</span>
            </button>
            <button onClick={() => setCurrentView('data')} className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-xl transition-all duration-200 ${currentView === 'data' ? 'bg-violet-500/15 text-violet-300 font-medium' : 'text-[#cbc3d7] hover:bg-white/5 hover:text-white'}`}>
              <Database size={18} />
              <span className="text-sm">Dashboards</span>
            </button>
          </div>

          <div>
             <div className="px-4 text-[11px] font-semibold text-[#cbc3d7] uppercase tracking-wider mb-2">
                Recent Chats
             </div>
             <div className="space-y-1">
                {sessions.length ? sessions.map((session) => (
                  <button
                    key={session.id}
                    onClick={() => loadSession(session.id)}
                    className={`w-full flex items-center gap-3 px-4 py-2 rounded-xl transition-all text-sm group ${session.id === currentSessionId ? 'bg-violet-500/15 text-violet-300' : 'text-[#cbc3d7] hover:bg-white/5 hover:text-white'}`}
                  >
                    <MessageSquare size={16} className="text-violet-400/70 group-hover:text-violet-400 shrink-0" />
                    <span className="truncate">{session.title || 'New Chat'}</span>
                  </button>
                )) : (
                  <div className="px-4 py-2 text-xs text-[#cbc3d7]/70">No saved chats yet</div>
                )}
             </div>
          </div>

          <div>
             <div className="px-4 text-[11px] font-semibold text-[#cbc3d7] uppercase tracking-wider mb-2 flex items-center justify-between">
                <span>Recent Datasets</span>
                <Plus size={14} className="cursor-pointer hover:text-white" />
             </div>
             <div className="space-y-1">
                {recentDatasets.length ? recentDatasets.map((item) => (
                  <button
                    key={item.id}
                    onClick={() => loadSession(item.session_id)}
                    className="w-full flex items-center gap-3 px-4 py-2 rounded-xl text-[#cbc3d7] hover:bg-white/5 hover:text-white transition-all text-sm group"
                  >
                     <Table size={16} className="text-violet-400/70 group-hover:text-violet-400 shrink-0"/>
                     <span className="truncate">{item.filename}</span>
                     <span className="ml-auto text-[10px] text-[#cbc3d7]/60 shrink-0">{formatNumber(item.row_count)} rows</span>
                  </button>
                )) : (
                  <div className="px-4 py-2 text-xs text-[#cbc3d7]/70">Upload a dataset to pin it here</div>
                )}
             </div>
          </div>

          <div>
             <h3 className="px-4 text-[11px] font-semibold text-[#cbc3d7] uppercase tracking-wider mb-2">Capabilities</h3>
             <div className="space-y-1">
                <button className="w-full flex items-center gap-3 px-4 py-2 rounded-xl text-[#cbc3d7] hover:bg-white/5 hover:text-white transition-all text-sm group">
                   <BarChart2 size={16} className="text-violet-400/70 group-hover:text-violet-400 shrink-0" />
                   <span className="truncate">EDA Copilot</span>
                </button>
                <button className="w-full flex items-center gap-3 px-4 py-2 rounded-xl text-[#cbc3d7] hover:bg-white/5 hover:text-white transition-all text-sm group">
                   <Store size={16} className="text-blue-400/70 group-hover:text-blue-400 shrink-0" />
                   <span className="truncate">Retail Analyst</span>
                </button>
                <button className="w-full flex items-center gap-3 px-4 py-2 rounded-xl text-[#cbc3d7] hover:bg-white/5 hover:text-white transition-all text-sm group">
                   <BrainCircuit size={16} className="text-amber-500/70 group-hover:text-amber-500 shrink-0" />
                   <span className="truncate">AutoML Studio</span>
                </button>
                <button className="w-full flex items-center gap-3 px-4 py-2 rounded-xl text-[#cbc3d7] hover:bg-white/5 hover:text-white transition-all text-sm group">
                   <Brain size={16} className="text-rose-400/70 group-hover:text-rose-400 shrink-0" />
                   <span className="truncate">Deep Analyze</span>
                </button>
             </div>
          </div>
        </nav>
        
        <div className="px-4 mt-auto border-t border-[#494454]/30 pt-4">
          <button className="w-full flex items-center gap-3 px-4 py-2.5 rounded-xl text-[#cbc3d7] hover:bg-white/5 hover:text-white transition-all duration-200">
            <Settings size={18} />
            <span className="text-sm">Settings</span>
          </button>
        </div>
      </aside>

      <div className="flex-1 flex flex-col relative h-full min-w-0">
        
        {/* --- Top Header Overlay --- */}
        <header className="absolute top-0 w-full z-40 bg-[#0b1326]/70 backdrop-blur-xl border-b border-[#494454]/30 shadow-sm flex items-center justify-between px-4 md:px-8 h-16">
          <div className="flex items-center gap-4">
            <button className="md:hidden text-[#cbc3d7] hover:text-white">
              <Menu size={24} />
            </button>
            <div className="hidden md:flex items-center gap-3">
              <h1 className="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-violet-400 to-blue-400">DataVerse AI</h1>
            </div>
            <div className="md:hidden flex items-center gap-3">
                <div className="w-8 h-8 rounded-full border border-violet-500/30 overflow-hidden">
                    <img src={USER_AVATAR} alt="User" className="w-full h-full object-cover" />
                </div>
                <h1 className="text-lg font-bold text-white">DataVerse AI</h1>
            </div>
          </div>
          
          <nav className="hidden md:flex items-center gap-8">
             <button onClick={() => setCurrentView('chat')} className={`text-sm font-medium transition-colors relative ${currentView === 'chat' ? 'text-violet-400' : 'text-[#cbc3d7] hover:text-white'}`}>
                Active Run
                {currentView === 'chat' && <span className="absolute -bottom-5 left-0 w-full h-[2px] bg-violet-400 rounded-t-full shadow-[0_0_10px_rgba(139,92,246,0.8)]"></span>}
             </button>
             <button onClick={() => setCurrentView('data')} className={`text-sm font-medium transition-colors relative ${currentView === 'data' ? 'text-violet-400' : 'text-[#cbc3d7] hover:text-white'}`}>
                Dashboards
                 {currentView === 'data' && <span className="absolute -bottom-5 left-0 w-full h-[2px] bg-violet-400 rounded-t-full shadow-[0_0_10px_rgba(139,92,246,0.8)]"></span>}
             </button>
          </nav>
        </header>

        {/* --- Main Content Area --- */}
        <AnimatePresence mode="wait">
          <motion.div 
            key={currentView}
            initial={{ opacity: 0, x: 10 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -10 }}
            transition={{ duration: 0.2 }}
            className="w-full h-full flex flex-col"
          >
            {currentView === 'home' && <HomeView dataset={dataset} uploadStatus={uploadStatus} onUpload={handleUpload} onSubmit={handleSubmit} />}
            {currentView === 'chat' && <ChatView dataset={dataset} messages={messages} isQuerying={isQuerying} onUpload={handleUpload} onSubmit={handleSubmit} />}
            {currentView === 'data' && <DataHubView dataset={dataset} messages={messages} onUpload={handleUpload} onSubmit={handleSubmit} />}
          </motion.div>
        </AnimatePresence>
        
        {/* --- Mobile Bottom Nav --- */}
        <nav className="md:hidden fixed bottom-6 left-1/2 -translate-x-1/2 w-[calc(100%-32px)] max-w-sm rounded-[2rem] z-50 bg-[#222a3d]/90 backdrop-blur-2xl border border-[#494454]/50 shadow-[0px_8px_32px_rgba(0,0,0,0.5)] flex items-center justify-between px-2 py-2">
           <button onClick={() => setCurrentView('home')} className={`p-3.5 rounded-full transition-all duration-300 flex items-center justify-center ${currentView === 'home' ? 'bg-gradient-to-r from-violet-500 to-blue-500 text-white shadow-lg scale-105' : 'text-[#cbc3d7] hover:text-white'}`}>
              <FolderOpen size={20} />
           </button>
           <button onClick={() => setCurrentView('chat')} className={`p-3.5 rounded-full transition-all duration-300 flex items-center justify-center ${currentView === 'chat' ? 'bg-gradient-to-r from-violet-500 to-blue-500 text-white shadow-lg scale-105' : 'text-[#cbc3d7] hover:text-white'}`}>
              <History size={20} />
           </button>
           <button onClick={() => setCurrentView('data')} className={`p-3.5 rounded-full transition-all duration-300 flex items-center justify-center ${currentView === 'data' ? 'bg-gradient-to-r from-violet-500 to-blue-500 text-white shadow-lg scale-105' : 'text-[#cbc3d7] hover:text-white'}`}>
              <Database size={20} />
           </button>
           <button className="p-3.5 rounded-full transition-all duration-300 flex items-center justify-center text-[#cbc3d7] hover:text-white">
              <Settings size={20} />
           </button>
        </nav>

      </div>
    </div>
  );
}

