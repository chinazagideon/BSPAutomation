import React, { useState } from 'react';
import {
  Activity,
  ExternalLink,
  Search,
  Filter,
  Trash2,
  Cpu,
  Zap,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Layers,
  ArrowUpRight,
  TrendingUp,
} from 'lucide-react';
import { TelemetryEventRecord } from '../types';

interface TelemetryExplorerProps {
  telemetryEvents: TelemetryEventRecord[];
  onClearTelemetry?: () => Promise<void>;
  jaegerUiUrl?: string;
}

export const TelemetryExplorer: React.FC<TelemetryExplorerProps> = ({
  telemetryEvents,
  onClearTelemetry,
  jaegerUiUrl = 'http://localhost:16686',
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [levelFilter, setLevelFilter] = useState<string>('all');
  const [selectedTraceId, setSelectedTraceId] = useState<string | null>(null);

  // Derive Top-Line Metrics
  const totalEvents = telemetryEvents.length;
  const traces = Array.from(new Set(telemetryEvents.map((e) => e.trace_id).filter(Boolean)));
  const fastPathEvents = telemetryEvents.filter(
    (e) => e.stage === 'STAGE_1_FAST_PATH' || e.event.includes('fast_path_matched')
  );
  const fastPathRate = totalEvents > 0 ? Math.round((fastPathEvents.length / Math.max(1, traces.length)) * 100) : 0;

  const warningOrErrorEvents = telemetryEvents.filter(
    (e) => e.level.toLowerCase() === 'warning' || e.level.toLowerCase() === 'error'
  );

  const latencies = telemetryEvents.map((e) => e.latency_ms || 0).filter((l) => l > 0);
  const avgLatency = latencies.length > 0 ? (latencies.reduce((a, b) => a + b, 0) / latencies.length).toFixed(1) : '0';

  // Group events by trace_id
  const traceMap = telemetryEvents.reduce<Record<string, TelemetryEventRecord[]>>((acc, ev) => {
    const key = ev.trace_id || 'unassigned';
    if (!acc[key]) acc[key] = [];
    acc[key].push(ev);
    return acc;
  }, {});

  const filteredTraceIds = Object.keys(traceMap).filter((tid) => {
    const events = traceMap[tid];
    const matchesSearch =
      searchTerm === '' ||
      tid.toLowerCase().includes(searchTerm.toLowerCase()) ||
      events.some(
        (e) =>
          e.event.toLowerCase().includes(searchTerm.toLowerCase()) ||
          (e.intent && e.intent.toLowerCase().includes(searchTerm.toLowerCase()))
      );

    const matchesLevel =
      levelFilter === 'all' || events.some((e) => e.level.toLowerCase() === levelFilter);

    return matchesSearch && matchesLevel;
  });

  const activeTraceEvents = selectedTraceId
    ? traceMap[selectedTraceId] || []
    : filteredTraceIds.length > 0
    ? traceMap[filteredTraceIds[0]] || []
    : [];

  const currentActiveTraceId = selectedTraceId || filteredTraceIds[0] || null;

  return (
    <div className="space-y-6">
      {/* Top Banner / Metrics Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-[#151518] border border-white/5 p-4 rounded-2xl shadow-sm space-y-1">
          <div className="flex items-center justify-between text-gray-400 text-xs">
            <span>Captured Traces</span>
            <Activity className="w-4 h-4 text-cyan-400" />
          </div>
          <div className="text-2xl font-bold font-mono text-white tracking-tight">
            {traces.length}
          </div>
          <p className="text-[11px] text-gray-500">Total conversation turns correlated</p>
        </div>

        <div className="bg-[#151518] border border-white/5 p-4 rounded-2xl shadow-sm space-y-1">
          <div className="flex items-center justify-between text-gray-400 text-xs">
            <span>Fast-Path 0-Token Ratio</span>
            <Zap className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-2xl font-bold font-mono text-emerald-400 tracking-tight">
            {fastPathRate}%
          </div>
          <p className="text-[11px] text-gray-500">Stage 1 Trigram & Slang hits</p>
        </div>

        <div className="bg-[#151518] border border-white/5 p-4 rounded-2xl shadow-sm space-y-1">
          <div className="flex items-center justify-between text-gray-400 text-xs">
            <span>Mean Pipeline Latency</span>
            <Clock className="w-4 h-4 text-purple-400" />
          </div>
          <div className="text-2xl font-bold font-mono text-purple-400 tracking-tight">
            {avgLatency} <span className="text-sm font-normal text-gray-400">ms</span>
          </div>
          <p className="text-[11px] text-gray-500">From webhook ACK to response strategy</p>
        </div>

        <div className="bg-[#151518] border border-white/5 p-4 rounded-2xl shadow-sm space-y-1">
          <div className="flex items-center justify-between text-gray-400 text-xs">
            <span>LLM Warnings & Retries</span>
            <AlertTriangle className="w-4 h-4 text-amber-400" />
          </div>
          <div className="text-2xl font-bold font-mono text-amber-400 tracking-tight">
            {warningOrErrorEvents.length}
          </div>
          <p className="text-[11px] text-gray-500">Gemini 429 quota, 503s & fallbacks</p>
        </div>
      </div>

      {/* Main Explorer Two-Column Workspace */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Column: Trace List & Filter Toolbar */}
        <div className="lg:col-span-5 space-y-3">
          <div className="bg-[#151518] border border-white/5 p-3 rounded-2xl space-y-2.5">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-xs text-gray-200 flex items-center gap-1.5">
                <Layers className="w-3.5 h-3.5 text-cyan-400" />
                Distributed Trace Catalog
              </span>
              <div className="flex items-center gap-1.5">
                <a
                  href={jaegerUiUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center gap-1 text-[11px] text-cyan-400 hover:text-cyan-300 bg-cyan-500/10 hover:bg-cyan-500/20 border border-cyan-500/20 px-2 py-0.5 rounded-lg transition-colors font-medium"
                >
                  <span>Launch Jaeger</span>
                  <ExternalLink className="w-2.5 h-2.5" />
                </a>
                {onClearTelemetry && (
                  <button
                    onClick={() => onClearTelemetry()}
                    title="Clear Telemetry History"
                    className="p-1 rounded text-gray-400 hover:text-red-400 hover:bg-white/5 transition-colors"
                  >
                    <Trash2 className="w-3 h-3" />
                  </button>
                )}
              </div>
            </div>

            {/* Filter Search */}
            <div className="flex items-center gap-2">
              <div className="flex-1 relative">
                <Search className="w-3.5 h-3.5 text-gray-500 absolute left-2.5 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  placeholder="Filter by trace ID, event, intent..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="w-full bg-[#0a0a0b] text-gray-200 text-xs pl-8 pr-3 py-1.5 rounded-xl border border-white/5 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                />
              </div>
              <select
                value={levelFilter}
                onChange={(e) => setLevelFilter(e.target.value)}
                className="bg-[#0a0a0b] text-gray-300 text-xs px-2 py-1.5 rounded-xl border border-white/5 focus:outline-none"
              >
                <option value="all">All</option>
                <option value="info">Info</option>
                <option value="warning">Warn</option>
                <option value="error">Err</option>
              </select>
            </div>
          </div>

          {/* Trace Rows List */}
          <div className="space-y-2 max-h-[580px] overflow-y-auto pr-1">
            {filteredTraceIds.length === 0 ? (
              <div className="p-8 rounded-2xl bg-[#151518] border border-white/5 text-center text-xs text-gray-500 italic">
                No matching traces found.
              </div>
            ) : (
              filteredTraceIds.map((tid) => {
                const evs = traceMap[tid];
                const isSelected = tid === currentActiveTraceId;
                const hasWarn = evs.some((e) => e.level.toLowerCase() === 'warning');
                const hasErr = evs.some((e) => e.level.toLowerCase() === 'error');
                const primaryIntent = evs.find((e) => e.intent)?.intent;
                const primaryStage = evs.find((e) => e.stage)?.stage;
                const turnLatency = evs.reduce((a, b) => a + (b.latency_ms || 0), 0);

                return (
                  <div
                    key={tid}
                    onClick={() => setSelectedTraceId(tid)}
                    className={`p-3 rounded-2xl border cursor-pointer transition-all ${
                      isSelected
                        ? 'bg-cyan-950/20 border-cyan-500/40 shadow-sm'
                        : 'bg-[#151518] border-white/5 hover:border-white/15'
                    }`}
                  >
                    <div className="flex items-center justify-between text-xs mb-1.5">
                      <div className="flex items-center gap-1.5">
                        <span className="font-mono text-gray-300 font-medium">
                          {tid === 'unassigned' ? 'process.internal' : tid.slice(0, 12)}...
                        </span>
                        {hasErr ? (
                          <span className="text-[9px] px-1.5 py-0.2 rounded bg-red-500/20 text-red-300 font-mono">
                            ERROR
                          </span>
                        ) : hasWarn ? (
                          <span className="text-[9px] px-1.5 py-0.2 rounded bg-amber-500/20 text-amber-300 font-mono">
                            RETRY
                          </span>
                        ) : (
                          <span className="text-[9px] px-1.5 py-0.2 rounded bg-emerald-500/10 text-emerald-400 font-mono">
                            200 OK
                          </span>
                        )}
                      </div>

                      <span className="text-[11px] font-mono text-gray-400">
                        {turnLatency > 0 ? `${turnLatency.toFixed(1)}ms` : ''}
                      </span>
                    </div>

                    <div className="flex items-center justify-between text-[11px] text-gray-400">
                      <div className="flex items-center gap-1.5">
                        {primaryStage && (
                          <span className="text-purple-400 bg-purple-500/10 px-1.5 py-0.5 rounded text-[10px] font-mono">
                            {primaryStage}
                          </span>
                        )}
                        {primaryIntent && (
                          <span className="text-emerald-300 bg-emerald-500/10 px-1.5 py-0.5 rounded text-[10px] font-mono">
                            {primaryIntent}
                          </span>
                        )}
                      </div>
                      <span className="text-[10px] text-gray-500">{evs.length} events</span>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Right Column: Waterfall Step Inspector & Attributes */}
        <div className="lg:col-span-7 bg-[#151518] border border-white/5 rounded-2xl p-5 shadow-sm space-y-4">
          <div className="flex items-center justify-between border-b border-white/5 pb-3">
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-semibold text-white">Execution Waterfall Lineage</h3>
                {currentActiveTraceId && currentActiveTraceId !== 'unassigned' && (
                  <span className="text-[10px] font-mono text-cyan-400 bg-cyan-500/10 border border-cyan-500/20 px-2 py-0.5 rounded-full">
                    {currentActiveTraceId}
                  </span>
                )}
              </div>
              <p className="text-xs text-gray-500 mt-0.5">
                Timeline representation of decisions across Fast-Path, Custom Classifier, and LLM escalation.
              </p>
            </div>

            {currentActiveTraceId && currentActiveTraceId !== 'unassigned' && (
              <a
                href={`${jaegerUiUrl}/trace/${currentActiveTraceId}`}
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-1.5 text-xs text-black font-semibold bg-cyan-400 hover:bg-cyan-300 px-3 py-1.5 rounded-xl transition-colors shadow-sm"
              >
                <span>View in Jaeger UI</span>
                <ArrowUpRight className="w-3.5 h-3.5" />
              </a>
            )}
          </div>

          {activeTraceEvents.length === 0 ? (
            <div className="py-12 text-center text-xs text-gray-500 italic">
              Select a trace from the left panel to inspect its distributed execution lineage.
            </div>
          ) : (
            <div className="space-y-3">
              {activeTraceEvents.map((ev, index) => {
                const isWarn = ev.level.toLowerCase() === 'warning';
                const isErr = ev.level.toLowerCase() === 'error';

                return (
                  <div
                    key={ev.id || index}
                    className={`p-3.5 rounded-xl border font-mono text-xs space-y-2 ${
                      isErr
                        ? 'bg-red-950/20 border-red-500/30'
                        : isWarn
                        ? 'bg-amber-950/20 border-amber-500/30'
                        : 'bg-[#0a0a0b] border-white/5'
                    }`}
                  >
                    <div className="flex items-center justify-between text-[11px]">
                      <div className="flex items-center gap-2">
                        <span className="text-gray-500">#{index + 1}</span>
                        <span className="font-semibold text-gray-200">{ev.event}</span>
                        {ev.stage && (
                          <span className="text-[10px] bg-purple-500/10 text-purple-300 px-1.5 py-0.2 rounded border border-purple-500/20">
                            {ev.stage}
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-2 text-gray-400">
                        {ev.latency_ms !== undefined && ev.latency_ms !== null && (
                          <span className="text-emerald-400 font-bold">{ev.latency_ms} ms</span>
                        )}
                        <span className="text-[10px] text-gray-500">
                          {new Date(ev.timestamp).toLocaleTimeString()}
                        </span>
                      </div>
                    </div>

                    {/* Metadata Badges */}
                    <div className="flex flex-wrap gap-2 text-[10px]">
                      {ev.intent && (
                        <div className="bg-white/5 px-2 py-0.5 rounded text-gray-300">
                          intent: <strong className="text-emerald-400">{ev.intent}</strong>
                        </div>
                      )}
                      {ev.action && (
                        <div className="bg-white/5 px-2 py-0.5 rounded text-gray-300">
                          action: <strong className="text-purple-300">{ev.action}</strong>
                        </div>
                      )}
                      {ev.confidence !== undefined && ev.confidence !== null && (
                        <div className="bg-white/5 px-2 py-0.5 rounded text-gray-300">
                          confidence: <strong className="text-blue-300">{ev.confidence}</strong>
                        </div>
                      )}
                      {ev.model && (
                        <div className="bg-white/5 px-2 py-0.5 rounded text-gray-300">
                          model: <strong className="text-yellow-300">{ev.model}</strong>
                        </div>
                      )}
                      {ev.tokens_consumed !== undefined && (
                        <div className="bg-white/5 px-2 py-0.5 rounded text-gray-300">
                          tokens: <strong className="text-cyan-300">{ev.tokens_consumed}</strong>
                        </div>
                      )}
                    </div>

                    {/* Error / Warning Details */}
                    {ev.error && (
                      <div className="mt-2 p-2.5 rounded bg-black/60 border border-red-500/30 text-red-300 text-[11px] break-all">
                        {ev.error}
                      </div>
                    )}

                    {/* Raw Attributes JSON */}
                    {ev.attributes && Object.keys(ev.attributes).length > 0 && (
                      <details className="text-[10px] text-gray-500 pt-1">
                        <summary className="cursor-pointer hover:text-gray-300">
                          View Extra Attributes ({Object.keys(ev.attributes).length})
                        </summary>
                        <pre className="mt-1 bg-black/40 p-2 rounded text-gray-400 overflow-x-auto text-[10px]">
                          {JSON.stringify(ev.attributes, null, 2)}
                        </pre>
                      </details>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
