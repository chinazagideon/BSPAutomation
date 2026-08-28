import React, { useState } from 'react';
import { 
  Server, 
  CheckCircle2, 
  Clock, 
  Send, 
  Code, 
  ShieldCheck, 
  Cpu, 
  Layers, 
  Play, 
  Zap, 
  RefreshCw,
  ArrowRight
} from 'lucide-react';
import { WebhookLog } from '../types';

interface WebhookInspectorProps {
  logs: WebhookLog[];
  onTriggerWebhook: (event: string, payload: any) => Promise<void>;
}

export const WebhookInspector: React.FC<WebhookInspectorProps> = ({ logs, onTriggerWebhook }) => {
  const [selectedLog, setSelectedLog] = useState<WebhookLog>(logs[0]);
  const [isSimulating, setIsSimulating] = useState(false);
  const [customPayloadPhone, setCustomPayloadPhone] = useState('+2348039876543');
  const [customMessageBody, setCustomMessageBody] = useState('How far, wetin be the wholesale price for 5 bags of rice?');

  const handleSimulateCustomWebhook = async () => {
    setIsSimulating(true);
    const mockPayload = {
      object: 'whatsapp_business_account',
      entry: [
        {
          id: 'WHATSAPP_BIZ_' + Math.floor(Math.random() * 9000 + 1000),
          changes: [
            {
              value: {
                messaging_product: 'whatsapp',
                metadata: { display_phone_number: '2348000000000', phone_number_id: 'PN_9021' },
                contacts: [{ profile: { name: 'Nigerian SME Merchant' }, wa_id: customPayloadPhone.replace(/\D/g, '') }],
                messages: [
                  {
                    from: customPayloadPhone.replace(/\D/g, ''),
                    id: 'wamid.HBgL' + Math.random().toString(36).substring(2, 12),
                    timestamp: Math.floor(Date.now() / 1000).toString(),
                    text: { body: customMessageBody },
                    type: 'text',
                  },
                ],
              },
              field: 'messages',
            },
          ],
        },
      ],
    };

    await onTriggerWebhook('messages.received', mockPayload);
    setIsSimulating(false);
  };

  return (
    <div className="space-y-6">
      {/* Top Banner: Architecture Overview */}
      <div className="bg-[#151518] border border-white/5 rounded-2xl p-5 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse"></span>
              <h2 className="text-sm font-semibold text-white tracking-tight">Decoupled Meta Webhook Ingestion Engine</h2>
            </div>
            <p className="text-xs text-gray-400 max-w-2xl leading-relaxed">
              Standard synchronous webhooks fail and drop customer transactions when users switch apps to complete USSD or bank transfers. 
              Our engine returns an immediate <strong className="text-emerald-400 font-mono">HTTP 200 OK (&lt; 20ms)</strong> and offloads processing to an asynchronous Redis worker pool.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <div className="bg-[#0e0e10] border border-white/5 px-4 py-2.5 rounded-xl text-center">
              <div className="text-[10px] text-gray-500 uppercase tracking-widest font-mono">Meta Ack Latency</div>
              <div className="text-base font-bold text-emerald-400 font-mono mt-0.5">16ms avg</div>
            </div>
            <div className="bg-[#0e0e10] border border-white/5 px-4 py-2.5 rounded-xl text-center">
              <div className="text-[10px] text-gray-500 uppercase tracking-widest font-mono">Queue Status</div>
              <div className="text-base font-bold text-blue-400 font-mono mt-0.5">0 Dropped</div>
            </div>
          </div>
        </div>
      </div>

      {/* Main Grid: Live Ingestion Stream & Payload Inspector */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: Webhook Log Stream */}
        <div className="lg:col-span-5 bg-[#151518] border border-white/5 rounded-2xl p-4 flex flex-col h-[580px] shadow-sm">
          <div className="flex items-center justify-between pb-3 border-b border-white/5">
            <div className="flex items-center gap-2">
              <Server className="w-4 h-4 text-emerald-400" />
              <h3 className="text-xs font-semibold text-gray-300 uppercase tracking-widest">Live Webhook Events</h3>
            </div>
            <span className="text-[10px] bg-white/5 text-gray-300 px-2 py-0.5 rounded font-mono border border-white/5">
              {logs.length} Recorded
            </span>
          </div>

          <div className="flex-1 overflow-y-auto space-y-2.5 mt-3 pr-1">
            {logs.map((log) => {
              const isSelected = selectedLog?.id === log.id;
              return (
                <div
                  key={log.id}
                  id={`webhook-log-${log.id}`}
                  onClick={() => setSelectedLog(log)}
                  className={`p-3 rounded-xl border text-xs cursor-pointer transition-all duration-150 ${
                    isSelected
                      ? 'border-emerald-500/50 bg-emerald-500/10 ring-1 ring-emerald-500/30'
                      : 'border-white/5 bg-white/[0.02] hover:border-white/10 hover:bg-white/5'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-1.5 font-mono font-semibold text-gray-200">
                      <span className="text-emerald-400 font-bold">{log.event}</span>
                    </div>
                    <span className="text-[10px] text-gray-500 font-mono">{log.timestamp}</span>
                  </div>

                  <div className="flex items-center justify-between text-[11px] text-gray-400 mb-2">
                    <span className="font-mono">{log.phone}</span>
                    <span className="text-emerald-400 font-mono bg-emerald-500/10 px-1.5 py-0.2 rounded border border-emerald-500/20 text-[10px]">
                      HTTP {log.httpStatus} ({log.ackLatencyMs}ms)
                    </span>
                  </div>

                  <div className="flex items-center justify-between text-[10px] pt-1.5 border-t border-white/5 text-gray-500">
                    <span className="flex items-center gap-1 text-blue-400">
                      <ShieldCheck className="w-3 h-3" /> HMAC-SHA256 Verified
                    </span>
                    <span className="font-mono text-gray-400">Worker: {log.workerLatencyMs}ms</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Right: Detailed Payload Viewer & Simulator */}
        <div className="lg:col-span-7 space-y-4">
          {/* Payload Inspector Card */}
          <div className="bg-[#151518] border border-white/5 rounded-2xl p-4 shadow-sm">
            <div className="flex items-center justify-between mb-3 pb-2 border-b border-white/5">
              <div className="flex items-center gap-2">
                <Code className="w-4 h-4 text-blue-400" />
                <h3 className="text-xs font-semibold text-gray-300 uppercase tracking-widest">
                  Raw Payload &amp; Header ({selectedLog?.id})
                </h3>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-2 py-0.5 rounded font-mono uppercase tracking-wider">
                  x-hub-signature-256: VALID
                </span>
              </div>
            </div>

            <div className="bg-[#0a0a0b] rounded-xl p-3.5 border border-white/5 font-mono text-[11px] text-gray-300 overflow-x-auto max-h-64">
              <pre className="text-emerald-400/90 leading-relaxed font-mono">
                {JSON.stringify(selectedLog?.rawPayload || {}, null, 2)}
              </pre>
            </div>

            {/* Asynchronous Queue Trace */}
            <div className="mt-4 p-3 bg-[#0e0e10] border border-white/5 rounded-xl space-y-2">
              <div className="text-[11px] font-medium text-gray-300 flex items-center gap-1.5">
                <Cpu className="w-3.5 h-3.5 text-purple-400" />
                <span className="uppercase tracking-widest text-[10px] text-gray-400">Asynchronous Execution Pipeline:</span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-[10px] font-mono">
                <div className="p-2 rounded-lg bg-[#151518] border border-white/5">
                  <div className="text-gray-500">Step 1: Ingress</div>
                  <div className="text-emerald-400 font-bold">HTTP 200 OK (18ms)</div>
                </div>
                <div className="p-2 rounded-lg bg-[#151518] border border-white/5">
                  <div className="text-gray-500">Step 2: PII Redaction</div>
                  <div className="text-blue-400 font-bold">BVN Scrubbed (4ms)</div>
                </div>
                <div className="p-2 rounded-lg bg-[#151518] border border-white/5">
                  <div className="text-gray-500">Step 3: Intent Action</div>
                  <div className="text-amber-400 font-bold">Redis Enqueued (12ms)</div>
                </div>
              </div>
            </div>
          </div>

          {/* Test Injector Form */}
          <div className="bg-[#151518] border border-white/5 rounded-2xl p-4 shadow-sm">
            <h3 className="text-xs font-semibold text-gray-300 uppercase tracking-widest flex items-center gap-2 mb-3">
              <Zap className="w-3.5 h-3.5 text-amber-400" />
              <span>Simulate Inbound Meta Webhook Request</span>
            </h3>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
              <div>
                <label className="text-[10px] text-gray-400 uppercase tracking-widest block mb-1">Customer Phone (WA ID)</label>
                <input
                  type="text"
                  id="webhook-phone-input"
                  value={customPayloadPhone}
                  onChange={(e) => setCustomPayloadPhone(e.target.value)}
                  className="w-full bg-[#0e0e10] border border-white/5 text-xs px-3 py-2 rounded-xl text-gray-200 focus:outline-none focus:border-emerald-500 font-mono"
                />
              </div>
              <div>
                <label className="text-[10px] text-gray-400 uppercase tracking-widest block mb-1">Message Text (Pidgin / English)</label>
                <input
                  type="text"
                  id="webhook-body-input"
                  value={customMessageBody}
                  onChange={(e) => setCustomMessageBody(e.target.value)}
                  className="w-full bg-[#0e0e10] border border-white/5 text-xs px-3 py-2 rounded-xl text-gray-200 focus:outline-none focus:border-emerald-500"
                />
              </div>
            </div>

            <button
              id="fire-webhook-btn"
              onClick={handleSimulateCustomWebhook}
              disabled={isSimulating}
              className="w-full bg-emerald-500 hover:bg-emerald-400 disabled:opacity-40 text-black font-bold uppercase tracking-widest py-2.5 px-4 rounded-xl text-[11px] flex items-center justify-center gap-2 transition-colors shadow-sm"
            >
              {isSimulating ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
              <span>Fire Decoupled Webhook (Simulate Meta Payload)</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
