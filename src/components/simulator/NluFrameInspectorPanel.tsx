import React from 'react';
import { Activity, Layers } from 'lucide-react';
import { SandboxNegotiationFrame, SandboxNluController } from '../../types';

interface NluFrameInspectorPanelProps {
  nluController: SandboxNluController;
  activeFrame: SandboxNegotiationFrame | null;
  onUpdateNluController?: (updates: Partial<SandboxNluController>) => Promise<void>;
}

const NLU_STAGE_TOGGLES: Array<{
  key: 'use_fast_path' | 'use_custom_model' | 'use_llm_escalation';
  label: string;
}> = [
  {
    key: 'use_fast_path',
    label: 'Stage 1: Fast-Path Trigram & Slang Router (0 tokens)',
  },
  {
    key: 'use_custom_model',
    label: 'Stage 2: Custom Local ONNX Classifier (0 tokens)',
  },
  {
    key: 'use_llm_escalation',
    label: 'Stage 3: Gemini 3.7 Flash / Context LLM Escalation',
  },
];

export const NluFrameInspectorPanel: React.FC<NluFrameInspectorPanelProps> = ({
  nluController,
  activeFrame,
  onUpdateNluController,
}) => {
  return (
    <div className="space-y-3 text-xs">
      <div className="p-3 rounded-xl bg-[#0e0e10] border border-white/5 space-y-2">
        <div className="font-semibold text-gray-200 flex items-center gap-1.5">
          <Layers className="w-3.5 h-3.5 text-purple-400" />
          <span>3-Stage Cascading NLU State Controllers</span>
        </div>
        <p className="text-[11px] text-gray-400">
          Toggle individual stages on/off at runtime to isolate and test Stage 1 (Trigram/Slang), Stage 2 (ONNX Local Model), or Stage 3 (LLM Escalation).
        </p>

        {NLU_STAGE_TOGGLES.map((st) => (
          <label
            key={st.key}
            className="flex items-center justify-between py-1 cursor-pointer text-[11px] text-gray-300 hover:text-white"
          >
            <span>{st.label}</span>
            <input
              type="checkbox"
              checked={Boolean(nluController[st.key])}
              onChange={(e) => onUpdateNluController?.({ [st.key]: e.target.checked })}
              className="rounded border-white/20 bg-black text-emerald-500 focus:ring-emerald-500"
            />
          </label>
        ))}
      </div>

      {/* Live Redis NegotiationFrame Inspector */}
      <div className="p-3 rounded-xl bg-[#0e0e10] border border-white/5 space-y-2">
        <div className="flex items-center justify-between">
          <span className="font-semibold text-gray-200 flex items-center gap-1.5">
            <Activity className="w-3.5 h-3.5 text-emerald-400" />
            Active NegotiationFrame (15m Sliding TTL)
          </span>
          <span className="text-[10px] font-mono text-gray-400">
            {activeFrame ? 'ACTIVE' : 'EMPTY'}
          </span>
        </div>
        {activeFrame ? (
          <div className="space-y-1.5 font-mono text-[11px] bg-black/40 p-2.5 rounded-lg border border-white/5">
            <div className="flex justify-between">
              <span className="text-gray-400">Tool:</span>
              <span className="text-emerald-400">{activeFrame.active_tool}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-400">Intent:</span>
              <span className="text-purple-300">{activeFrame.intent}</span>
            </div>
            <div>
              <span className="text-gray-400 block mb-0.5">Bound Slots:</span>
              <pre className="text-[10px] text-emerald-300 bg-[#151518] p-1.5 rounded overflow-x-auto">
                {JSON.stringify(activeFrame.bound_slots, null, 2)}
              </pre>
            </div>
            {activeFrame.missing_slots?.length > 0 && (
              <div className="flex justify-between">
                <span className="text-gray-400">Missing Slots:</span>
                <span className="text-amber-300">{activeFrame.missing_slots.join(', ')}</span>
              </div>
            )}
            {activeFrame.pending_offer && (
              <div>
                <span className="text-gray-400 block mb-0.5">Pending Offer:</span>
                <pre className="text-[10px] text-blue-300 bg-[#151518] p-1.5 rounded overflow-x-auto">
                  {JSON.stringify(activeFrame.pending_offer, null, 2)}
                </pre>
              </div>
            )}
          </div>
        ) : (
          <p className="text-[11px] text-gray-500 italic">
            No active slot-filling frame. Ask for a product price or tap [Order Now] on a catalog card to inspect live slot binding.
          </p>
        )}
      </div>
    </div>
  );
};
