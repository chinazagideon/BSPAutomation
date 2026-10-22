import React from 'react';
import { ChevronRight } from 'lucide-react';

interface ScenarioPreset {
  id: string;
  title: string;
  text: string;
  description: string;
}

const PRESETS: ScenarioPreset[] = [
  {
    id: 'catalog-browse',
    title: '🛒 Interactive Catalog & Slot Negotiation',
    text: 'How much be rice for una store?',
    description: 'Triggers Interactive List Picker -> 3-Button Product Card -> Multi-turn Slot-Filling.',
  },
  {
    id: 'pidgin-order',
    title: '🇳🇬 Pidgin Wholesale Order',
    text: 'How far! I wan order 3 bags of Mama Gold Rice 50kg make una deliver to Ikeja.',
    description: 'Tests fast-path Nigerian Pidgin intent + 10m anti-ghosting checkout hold.',
  },
  {
    id: 'bvn-sanitization',
    title: '🛡️ PII BVN/NIN Redaction',
    text: 'Good day, please verify my business account. My BVN is 22298765432 and my account number is 0123456789 (Access Bank).',
    description: 'Tests NDPA pre-processing regex scrubbing before routing to NLU/LLM.',
  },
  {
    id: 'transfer-proof',
    title: '💳 Debit Alert Confirmation',
    text: 'I don transfer ₦73,500 to the Moniepoint account. Check your alert, receipt is attached.',
    description: 'Triggers instant double-entry ledger reconciliation and receipt push.',
  },
  {
    id: 'opt-out-compliance',
    title: '🛑 NDPA Opt-Out Keyword (COMOT / STOP)',
    text: 'COMOT abeg stop sending me messages',
    description: 'Tests deterministic NDPA opt-out interceptor & SHA-256 chained consent ledger.',
  },
  {
    id: 'agent-escalation',
    title: '👨‍💼 Resilient Agent Handoff',
    text: 'I have a complex logistics API question for our nationwide fleet. Talk to human agent abeg.',
    description: 'Generates 6-field AI context injection card and escalates to live desk.',
  },
];

interface ScenarioPresetsPanelProps {
  selectedPreset: string | null;
  onSelectPreset: (id: string, text: string) => void;
}

export const ScenarioPresetsPanel: React.FC<ScenarioPresetsPanelProps> = ({
  selectedPreset,
  onSelectPreset,
}) => {
  return (
    <div className="space-y-2">
      <p className="text-xs text-gray-400 mb-2 leading-relaxed">
        Click any scenario or use the phone controls (Mic, Location, Interactive Lists/Buttons) to test full conversational fluency locally.
      </p>
      {PRESETS.map((preset) => (
        <button
          key={preset.id}
          id={`preset-${preset.id}`}
          onClick={() => onSelectPreset(preset.id, preset.text)}
          className={`w-full text-left p-2.5 rounded-xl border text-xs transition-all duration-150 ${
            selectedPreset === preset.id
              ? 'border-emerald-500/50 bg-emerald-500/10 text-emerald-300 ring-1 ring-emerald-500/30'
              : 'border-white/5 bg-white/[0.02] text-gray-300 hover:border-white/10 hover:bg-white/5'
          }`}
        >
          <div className="flex items-center justify-between font-medium mb-0.5">
            <span className="text-gray-200">{preset.title}</span>
            <ChevronRight className="w-3.5 h-3.5 text-gray-500" />
          </div>
          <div className="text-gray-400 text-[11px] line-clamp-1 italic mb-0.5">"{preset.text}"</div>
          <div className="text-[10px] text-emerald-400 font-mono">{preset.description}</div>
        </button>
      ))}
    </div>
  );
};
