import React, { useState } from 'react';
import {
  Activity,
  ExternalLink,
  Trash2,
  Filter,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Cpu,
  Zap,
  ArrowRight,
  Sparkles,
} from 'lucide-react';
import { TelemetryEventRecord } from '../../types';

interface TelemetryStreamPanelProps {
  telemetryEvents: TelemetryEventRecord[];
  onClearTelemetry?: () => Promise<void>;
  jaegerUiUrl?: string;
}

export const TelemetryStreamPanel: React.FC<TelemetryStreamPanelProps> = ({
  telemetryEvents,
  onClearTelemetry,
  jaegerUiUrl = 'http://localhost:16686',
}) => {
  const [filterLevel, setFilterLevel] = useState<string>('all');
  const [viewMode, setViewMode] = useState<'waterfall' | 'raw'>('waterfall');
  const [selectedTraceId, setSelectedTraceId] = useState<string | null>(null);

  const filteredEvents = telemetryEvents.filter((ev) => {
    if (filterLevel === 'all') return true;
    return ev.level.toLowerCase() === filterLevel;
  });

  // Group events by trace_id to display clean turn-by-turn waterfalls
  const traceGroups = filteredEvents.reduce<Record<string, TelemetryEventRecord[]>>((acc, ev) => {
    const key = ev.trace_id || 'no-trace';
    if (!acc[key]) acc[key] = [];
    acc[key].push(ev);
    return acc;
  }, {});

  const traceKeys = Object.keys(traceGroups);

  const getLevelBadge = (level: string) => {
    switch (level.toLowerCase()) {
      case 'warning':
      case 'warn':
        return (
          <span className="flex items-center gap-1 text-[9px] px-1.5 py-0.5 rounded font-mono bg-amber-500/10 text-amber-300 border border-amber-500/30">
            <AlertTriangle className="w-2.5 h-2.5" />
            WARN
          </span>
        );
      case 'error':
        return (
          <span className="flex items-center gap-1 text-[9px] px-1.5 py-0.5 rounded font-mono bg-red-500/10 text-red-300 border border-red-500/30">
            <XCircle className="w-2.5 h-2.5" />
            ERR
          </span>
        );
      default:
        return (
          <span className="flex items-center gap-1 text-[9px] px-1.5 py-0.5 rounded font-mono bg-emerald-500/10 text-emerald-300 border border-emerald-500/30">
            <CheckCircle2 className="w-2.5 h-2.5" />
            INFO
          </span>
        );
    }
  };

  return (
    <div className="space-y-3 text-xs">
      {/* Top Header & Toolbar */}
      <div className="p-3 rounded-xl bg-[#0e0e10] border border-white/5 space-y-2">
        <div className="flex items-center justify-between">
          <div className="font-semibold text-gray-200 flex items-center gap-1.5">
            <Activity className="w-3.5 h-3.5 text-cyan-400" />
            <span>OpenTelemetry & Pipeline Stream</span>
          </div>
          <div className="flex items-center gap-1.5">
            <a
              href={jaegerUiUrl}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1 text-[10px] text-cyan-400 hover:text-cyan-300 bg-cyan-500/10 hover:bg-cyan-500/20 border border-cyan-500/20 px-2 py-0.5 rounded-lg transition-colors"
            >
              <span>Jaeger UI</span>
              <ExternalLink className="w-2.5 h-2.5" />
            </a>
            {onClearTelemetry && (
              <button
                onClick={() => onClearTelemetry()}
                title="Clear local telemetry buffer"
                className="text-gray-400 hover:text-red-400 p-1 rounded hover:bg-white/5 transition-colors"
              >
                <Trash2 className="w-3 h-3" />
              </button>
            )}
          </div>
        </div>

        <p className="text-[11px] text-gray-400">
          Live correlation of <code className="text-gray-300">structlog</code> events with W3C distributed trace spans across Stage 1 Fast-Path, Local ONNX, and LLM escalation.
        </p>

        <div className="flex items-center justify-between pt-1 border-t border-white/5">
          <div className="flex items-center gap-1">
            <button
              onClick={() => setViewMode('waterfall')}
              className={`px-2 py-0.5 rounded text-[10px] font-medium transition-colors ${
                viewMode === 'waterfall'
                  ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/30'
                  : 'text-gray-400 hover:text-white bg-white/5'
              }`}
            >
              Trace Waterfalls
            </button>
            <button
              onClick={() => setViewMode('raw')}
              className={`px-2 py-0.5 rounded text-[10px] font-medium transition-colors ${
                viewMode === 'raw'
                  ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/30'
                  : 'text-gray-400 hover:text-white bg-white/5'
              }`}
            >
              Raw Event Feed
            </button>
          </div>

          <div className="flex items-center gap-1 text-[10px] text-gray-400">
            <Filter className="w-3 h-3 text-gray-500" />
            <select
              value={filterLevel}
              onChange={(e) => setFilterLevel(e.target.value)}
              className="bg-black/60 text-gray-300 border border-white/10 rounded px-1.5 py-0.5 focus:outline-none"
            >
              <option value="all">All Levels</option>
              <option value="info">Info</option>
              <option value="warning">Warn/Retry</option>
              <option value="error">Errors</option>
            </select>
          </div>
        </div>
      </div>

      {/* Main Content Area */}
      {viewMode === 'waterfall' ? (
        <div className="space-y-2.5 max-h-[380px] overflow-y-auto pr-1">
          {traceKeys.length === 0 ? (
            <div className="p-4 rounded-xl bg-[#0e0e10] border border-white/5 text-center text-[11px] text-gray-500 italic">
              No telemetry events captured yet. Send a message in the phone simulator to observe live traces.
            </div>
          ) : (
            traceKeys.map((traceId) => {
              const events = traceGroups[traceId];
              const isSelected = selectedTraceId === traceId;
              const hasWarning = events.some((e) => e.level === 'warning');
              const hasError = events.some((e) => e.level === 'error');
              const totalLatency = events.reduce((acc, e) => acc + (e.latency_ms || 0), 0);
              const primaryStage = events.find((e) => e.stage)?.stage || 'INFERENCE';

              return (
                <div
                  key={traceId}
                  className={`p-2.5 rounded-xl border transition-all ${
                    hasError
                      ? 'bg-red-950/20 border-red-500/30'
                      : hasWarning
                      ? 'bg-amber-950/20 border-amber-500/30'
                      : 'bg-[#0e0e10] border-white/5 hover:border-white/15'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2 mb-1.5">
                    <div className="flex items-center gap-1.5 overflow-hidden">
                      <span className="font-mono text-[10px] text-gray-400 truncate max-w-[150px]">
                        {traceId === 'no-trace' ? 'process.local' : `trace:${traceId.slice(0, 10)}...`}
                      </span>
                      {hasError ? (
                        <span className="text-[9px] px-1 py-0.2 rounded bg-red-500/20 text-red-300 font-mono">ERR</span>
                      ) : hasWarning ? (
                        <span className="text-[9px] px-1 py-0.2 rounded bg-amber-500/20 text-amber-300 font-mono">RETRY</span>
                      ) : (
                        <span className="text-[9px] px-1 py-0.2 rounded bg-cyan-500/10 text-cyan-300 font-mono">200 OK</span>
                      )}
                    </div>

                    <div className="flex items-center gap-2 flex-shrink-0">
                      {totalLatency > 0 && (
                        <span className="text-[10px] font-mono text-emerald-400">
                          {totalLatency.toFixed(1)}ms
                        </span>
                      )}
                      {traceId !== 'no-trace' && (
                        <a
                          href={`${jaegerUiUrl}/trace/${traceId}`}
                          target="_blank"
                          rel="noreferrer"
                          title="Open waterfall in Jaeger UI"
                          className="text-gray-400 hover:text-cyan-400"
                        >
                          <ExternalLink className="w-3 h-3" />
                        </a>
                      )}
                    </div>
                  </div>

                  {/* Waterfall Pipeline Steps */}
                  <div className="space-y-1 pt-1 border-t border-white/5">
                    {events.map((ev, idx) => (
                      <div
                        key={ev.id || idx}
                        className="flex items-center justify-between text-[10px] font-mono bg-black/40 px-2 py-1 rounded border border-white/5"
                      >
                        <div className="flex items-center gap-1.5 truncate">
                          {ev.stage ? (
                            <span className="text-purple-400 flex items-center gap-1">
                              <Cpu className="w-2.5 h-2.5" />
                              {ev.stage}
                            </span>
                          ) : ev.event.includes('retry') ? (
                            <span className="text-amber-300 flex items-center gap-1">
                              <AlertTriangle className="w-2.5 h-2.5" />
                              {ev.event}
                            </span>
                          ) : (
                            <span className="text-gray-300">{ev.event}</span>
                          )}

                          {ev.intent && (
                            <span className="text-emerald-400 bg-emerald-500/10 px-1 rounded">
                              {ev.intent}
                            </span>
                          )}
                        </div>

                        <div className="flex items-center gap-1.5 flex-shrink-0 text-gray-400">
                          {ev.latency_ms !== undefined && ev.latency_ms !== null && (
                            <span className="text-gray-400">{ev.latency_ms}ms</span>
                          )}
                          {getLevelBadge(ev.level)}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })
          )}
        </div>
      ) : (
        /* Raw Feed View */
        <div className="space-y-1.5 max-h-[380px] overflow-y-auto font-mono text-[10px] pr-1">
          {filteredEvents.length === 0 ? (
            <div className="p-4 rounded-xl bg-[#0e0e10] border border-white/5 text-center text-gray-500 italic">
              No matching events.
            </div>
          ) : (
            filteredEvents.map((ev) => (
              <div
                key={ev.id}
                className="p-2 rounded bg-[#0e0e10] border border-white/5 space-y-1 hover:border-white/10"
              >
                <div className="flex items-center justify-between text-gray-400">
                  <div className="flex items-center gap-1.5 truncate">
                    {getLevelBadge(ev.level)}
                    <span className="text-gray-200 font-semibold truncate">{ev.event}</span>
                  </div>
                  <span className="text-[9px] text-gray-500">
                    {new Date(ev.timestamp).toLocaleTimeString()}
                  </span>
                </div>

                <div className="text-gray-400 flex flex-wrap gap-x-3 gap-y-0.5 text-[9px]">
                  {ev.trace_id && (
                    <span>
                      trace: <code className="text-cyan-300">{ev.trace_id.slice(0, 8)}</code>
                    </span>
                  )}
                  {ev.latency_ms !== undefined && ev.latency_ms !== null && (
                    <span>
                      latency: <span className="text-emerald-300">{ev.latency_ms}ms</span>
                    </span>
                  )}
                  {ev.stage && (
                    <span>
                      stage: <span className="text-purple-300">{ev.stage}</span>
                    </span>
                  )}
                  {ev.intent && (
                    <span>
                      intent: <span className="text-amber-300">{ev.intent}</span>
                    </span>
                  )}
                </div>

                {ev.error && (
                  <p className="text-red-400 bg-red-950/30 p-1 rounded border border-red-500/20 text-[9px] break-all">
                    {ev.error}
                  </p>
                )}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
};
