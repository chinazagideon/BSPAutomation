import React from 'react';
import { AlertTriangle, Clock, Zap } from 'lucide-react';
import { SandboxFaultProfile, SandboxWindowState } from '../../types';

interface FaultInjectionPanelProps {
  isLoading: boolean;
  faultProfile: SandboxFaultProfile;
  windowState: SandboxWindowState;
  onUpdateFaultProfile?: (updates: Partial<SandboxFaultProfile>) => Promise<void>;
  onSendBurst?: (messages: string[]) => Promise<void>;
  onSendTemplate?: (templateName: string) => Promise<void>;
}

const FAULT_TOGGLES: Array<{
  key: keyof SandboxFaultProfile;
  label: string;
}> = [
  {
    key: 'corrupt_hmac_signature',
    label: 'Corrupt X-Hub-Signature-256 HMAC (Test 403 Reject)',
  },
  {
    key: 'force_rate_limit_429',
    label: 'Simulate BSP Egress HTTP 429 Rate Limit',
  },
  {
    key: 'force_upstream_500',
    label: 'Simulate BSP Egress HTTP 500 Outage',
  },
  {
    key: 'simulate_delivery_failure',
    label: 'Simulate Async Outbound Delivery Failure',
  },
  {
    key: 'duplicate_webhook_replay',
    label: 'Inject Duplicate Webhook Replay Event',
  },
];

export const FaultInjectionPanel: React.FC<FaultInjectionPanelProps> = ({
  isLoading,
  faultProfile,
  windowState,
  onUpdateFaultProfile,
  onSendBurst,
  onSendTemplate,
}) => {
  return (
    <div className="space-y-3 text-xs">
      {/* 1. Rapid Multi-Message Burst (1.2s Debounce Test) */}
      <div className="p-3 rounded-xl bg-[#0e0e10] border border-white/5 space-y-2">
        <div className="flex items-center justify-between">
          <span className="font-semibold text-gray-200 flex items-center gap-1.5">
            <Zap className="w-3.5 h-3.5 text-emerald-400" />
            Rapid 3-Message Burst (1.2s Debounce)
          </span>
          <span className="text-[10px] font-mono text-emerald-400">ADR-0043</span>
        </div>
        <p className="text-[11px] text-gray-400">
          Fires 3 overlapping customer messages 120ms apart to test Redis burst concatenation before NLU classification.
        </p>
        <button
          id="trigger-burst-btn"
          disabled={isLoading}
          onClick={() =>
            onSendBurst?.([
              'How far boss',
              'I wan order 2 bags of Mama Gold Rice 50kg',
              'make una deliver am to Ikeja',
            ])
          }
          className="w-full py-1.5 px-3 rounded-lg bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 border border-emerald-500/30 font-mono text-[11px] transition-colors"
        >
          ⚡ Fire 3-Message Rapid Burst Now
        </button>
      </div>

      {/* 2. 24-Hour Customer Service Window Governor */}
      <div className="p-3 rounded-xl bg-[#0e0e10] border border-white/5 space-y-2">
        <div className="flex items-center justify-between">
          <span className="font-semibold text-gray-200 flex items-center gap-1.5">
            <Clock className="w-3.5 h-3.5 text-amber-400" />
            24h Customer Service Window Governor
          </span>
          <span
            className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${
              windowState.is_open
                ? 'bg-emerald-500/10 text-emerald-400'
                : 'bg-red-500/20 text-red-400'
            }`}
          >
            {windowState.is_open
              ? `OPEN (${windowState.remaining_hours}h left)`
              : 'EXPIRED (>24h)'}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            id="expire-24h-window-btn"
            onClick={() =>
              onUpdateFaultProfile?.({
                clock_offset_hours: faultProfile.clock_offset_hours >= 24 ? 0 : 25,
              })
            }
            className={`flex-1 py-1.5 px-2.5 rounded-lg border font-mono text-[10px] transition-colors ${
              faultProfile.clock_offset_hours >= 24
                ? 'bg-red-500/20 border-red-500/40 text-red-300'
                : 'bg-white/5 border-white/10 text-gray-300 hover:bg-white/10'
            }`}
          >
            {faultProfile.clock_offset_hours >= 24
              ? '⏱️ Reset Clock (0h Offset)'
              : '⏱️ Fast-Forward +25h (Expire Window)'}
          </button>
          <button
            id="send-reengagement-template-btn"
            onClick={() => onSendTemplate?.('re_engagement_window_opener')}
            className="py-1.5 px-2.5 rounded-lg bg-blue-500/20 hover:bg-blue-500/30 border border-blue-500/30 text-blue-300 font-mono text-[10px]"
          >
            📋 Send Template
          </button>
        </div>
      </div>

      {/* 3. Transport & Webhook Chaos Toggles */}
      <div className="p-3 rounded-xl bg-[#0e0e10] border border-white/5 space-y-2">
        <div className="font-semibold text-gray-200 flex items-center gap-1.5 mb-1">
          <AlertTriangle className="w-3.5 h-3.5 text-red-400" />
          <span>Transport & Cryptographic Fault Injection</span>
        </div>

        {FAULT_TOGGLES.map((item) => (
          <label
            key={item.key}
            className="flex items-center justify-between py-1 cursor-pointer text-[11px] text-gray-300 hover:text-white"
          >
            <span>{item.label}</span>
            <input
              type="checkbox"
              checked={Boolean(faultProfile[item.key])}
              onChange={(e) => onUpdateFaultProfile?.({ [item.key]: e.target.checked })}
              className="rounded border-white/20 bg-black text-emerald-500 focus:ring-emerald-500"
            />
          </label>
        ))}
      </div>
    </div>
  );
};
