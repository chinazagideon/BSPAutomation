import React from 'react';
import { Radio } from 'lucide-react';
import { SandboxMerchant } from '../../types';

interface SimulatorControlBarProps {
  isBackendConnected: boolean;
  merchants: SandboxMerchant[];
  activePhoneNumberId: string;
  onSelectMerchantPhoneId?: (phoneNumberId: string) => void;
  activeProvider: string;
  onSelectProvider?: (provider: string) => void;
}

const PROVIDERS = [
  { slug: 'sandbox', label: 'Local Sandbox' },
  { slug: 'whatsapp', label: 'Meta Cloud' },
  { slug: 'meta', label: 'Meta Cloud v20.0' },
  { slug: 'termii', label: 'Termii NG' },
  { slug: 'twilio', label: 'Twilio Africa' },
  { slug: '360dialog', label: '360dialog' },
];

export const SimulatorControlBar: React.FC<SimulatorControlBarProps> = ({
  isBackendConnected,
  merchants,
  activePhoneNumberId,
  onSelectMerchantPhoneId,
  activeProvider,
  onSelectProvider,
}) => {
  return (
    <div className="bg-[#151518] border border-white/5 rounded-2xl p-3.5 shadow-sm space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Radio
            className={`w-3.5 h-3.5 ${
              isBackendConnected ? 'text-emerald-400 animate-pulse' : 'text-amber-400'
            }`}
          />
          <span className="text-[11px] font-semibold uppercase tracking-wider text-gray-300">
            Local BSP Sandbox Harness
          </span>
        </div>
        <span
          className={`text-[10px] font-mono px-2 py-0.5 rounded-full border ${
            isBackendConnected
              ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
              : 'bg-amber-500/10 text-amber-300 border-amber-500/30'
          }`}
        >
          {isBackendConnected ? 'Python FastAPI Connected' : 'Local Express Mode'}
        </span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 text-xs">
        <div>
          <label className="block text-[10px] text-gray-400 uppercase font-mono mb-1">
            Active Tenant (WABA)
          </label>
          <select
            id="sandbox-merchant-select"
            value={activePhoneNumberId}
            onChange={(e) => onSelectMerchantPhoneId?.(e.target.value)}
            className="w-full bg-[#0e0e10] border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-emerald-500"
          >
            {merchants.map((m) => (
              <option key={m.whatsapp_phone_number_id} value={m.whatsapp_phone_number_id}>
                {m.business_name}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-[10px] text-gray-400 uppercase font-mono mb-1">
            Webhook Provider Adapter
          </label>
          <select
            id="sandbox-provider-select"
            value={activeProvider}
            onChange={(e) => onSelectProvider?.(e.target.value)}
            className="w-full bg-[#0e0e10] border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-emerald-500 font-mono"
          >
            {PROVIDERS.map((p) => (
              <option key={p.slug} value={p.slug}>
                /webhooks/{p.slug} ({p.label})
              </option>
            ))}
          </select>
        </div>
      </div>
    </div>
  );
};
