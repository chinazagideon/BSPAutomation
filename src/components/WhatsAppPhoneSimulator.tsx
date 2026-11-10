import React, { useState, useEffect, useRef } from 'react';
import {
  Activity,
  Check,
  Flame,
  MapPin,
  Mic,
  RotateCcw,
  Send,
  ShieldAlert,
  Sliders,
  Sparkles,
} from 'lucide-react';
import { APP_CONFIG } from '../config/env';
import {
  ChatMessage,
  InteractiveListSection,
  SandboxFaultProfile,
  SandboxMerchant,
  SandboxNegotiationFrame,
  SandboxNluController,
  SandboxWindowState,
  TelemetryEventRecord,
} from '../types';
import { FaultInjectionPanel } from './simulator/FaultInjectionPanel';
import { InteractiveListDrawer } from './simulator/InteractiveListDrawer';
import { NluFrameInspectorPanel } from './simulator/NluFrameInspectorPanel';
import { PhoneChatBubble } from './simulator/PhoneChatBubble';
import { ScenarioPresetsPanel } from './simulator/ScenarioPresetsPanel';
import { SimulatorControlBar } from './simulator/SimulatorControlBar';
import { TelemetryStreamPanel } from './simulator/TelemetryStreamPanel';

const DEFAULT_MERCHANTS: SandboxMerchant[] = [
  {
    id: '018f6c5a-8b1e-7230-a890-111111111111',
    business_name: 'Alaba Agro & Commodities Depot',
    slug: 'alaba-agro',
    whatsapp_business_phone: '+2348011223301',
    whatsapp_phone_number_id: 'meta_phone_alaba_agro',
  },
  {
    id: '018f6c5a-8b1e-7230-a890-222222222222',
    business_name: 'Lekki Glow Wellness & Barber Hub',
    slug: 'lekki-glow',
    whatsapp_business_phone: '+2348011223302',
    whatsapp_phone_number_id: 'meta_phone_lekki_glow',
  },
  {
    id: '018f6c5a-8b1e-7230-a890-333333333333',
    business_name: 'Horizon Tech Gadgets Canary',
    slug: 'horizon-tech',
    whatsapp_business_phone: '+2348011223303',
    whatsapp_phone_number_id: 'meta_phone_horizon_tech',
  },
];

interface WhatsAppPhoneSimulatorProps {
  messages: ChatMessage[];
  onSendMessage: (
    text: string,
    options?: {
      messageType?: string;
      interactiveId?: string;
      mediaId?: string;
      reactionEmoji?: string;
      location?: Record<string, any>;
    }
  ) => Promise<void>;
  isLoading: boolean;
  onSimulateBankTransfer: (ref: string, amount: number) => void;
  activeHoldExpiry?: string;
  onResetChat: () => void;
  merchants?: SandboxMerchant[];
  activePhoneNumberId?: string;
  onSelectMerchantPhoneId?: (phoneNumberId: string) => void;
  activeProvider?: string;
  onSelectProvider?: (provider: string) => void;
  faultProfile?: SandboxFaultProfile;
  onUpdateFaultProfile?: (updates: Partial<SandboxFaultProfile>) => Promise<void>;
  nluController?: SandboxNluController;
  onUpdateNluController?: (updates: Partial<SandboxNluController>) => Promise<void>;
  windowState?: SandboxWindowState;
  activeFrame?: SandboxNegotiationFrame | null;
  onSendBurst?: (messages: string[]) => Promise<void>;
  onSendTemplate?: (templateName: string) => Promise<void>;
  isBackendConnected?: boolean;
  telemetryEvents?: TelemetryEventRecord[];
  onClearTelemetry?: () => Promise<void>;
  jaegerUiUrl?: string;
}

export const WhatsAppPhoneSimulator: React.FC<WhatsAppPhoneSimulatorProps> = ({
  messages,
  onSendMessage,
  isLoading,
  onSimulateBankTransfer,
  onResetChat,
  merchants = DEFAULT_MERCHANTS,
  activePhoneNumberId = APP_CONFIG.DEFAULT_PHONE_NUMBER_ID,
  onSelectMerchantPhoneId,
  activeProvider = APP_CONFIG.DEFAULT_PROVIDER,
  onSelectProvider,
  faultProfile = {
    force_rate_limit_429: false,
    force_upstream_500: false,
    simulate_delivery_failure: false,
    enforce_24h_window: true,
    clock_offset_hours: 0,
    duplicate_webhook_replay: false,
    corrupt_hmac_signature: false,
    network_latency_ms: 0,
  },
  onUpdateFaultProfile,
  nluController = {
    use_fast_path: true,
    fast_path_confidence_threshold: 0.9,
    use_custom_model: true,
    custom_model_confidence_threshold: 0.75,
    use_llm_escalation: true,
    active_bsp_provider: 'META_CLOUD',
  },
  onUpdateNluController,
  windowState = {
    is_open: true,
    elapsed_hours: 0.0,
    remaining_seconds: 86400,
    remaining_hours: 24.0,
    clock_offset_hours: 0,
    enforce_24h_window: true,
  },
  activeFrame = null,
  onSendBurst,
  onSendTemplate,
  isBackendConnected = false,
  telemetryEvents = [],
  onClearTelemetry,
  jaegerUiUrl,
}) => {
  const [inputText, setInputText] = useState('');
  const [remainingHoldSeconds, setRemainingHoldSeconds] = useState(600);
  const [selectedPreset, setSelectedPreset] = useState<string | null>(null);
  const [leftTab, setLeftTab] = useState<'scenarios' | 'chaos' | 'nlu' | 'telemetry'>('scenarios');
  const [openListDrawer, setOpenListDrawer] = useState<{
    title: string;
    sections: InteractiveListSection[];
  } | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const currentMerchant =
    merchants.find((m) => m.whatsapp_phone_number_id === activePhoneNumberId) || merchants[0];

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  useEffect(() => {
    const timer = setInterval(() => {
      setRemainingHoldSeconds((prev) => (prev > 0 ? prev - 1 : 0));
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  const handleSend = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!inputText.trim() || isLoading) return;
    const textToSend = inputText;
    setInputText('');
    await onSendMessage(textToSend, { messageType: 'text' });
  };

  const handleInteractiveTap = async (
    id: string,
    title: string,
    type: 'button_reply' | 'list_reply'
  ) => {
    setOpenListDrawer(null);
    await onSendMessage(title, {
      messageType: type,
      interactiveId: id,
    });
  };

  const handleSendVoiceNote = async () => {
    if (isLoading) return;
    const mediaId = `vn_lagos_${Math.floor(Math.random() * 9000 + 1000)}`;
    await onSendMessage(`[Voice Note: ${mediaId}]`, {
      messageType: 'audio',
      mediaId,
    });
  };

  const handleShareLocation = async () => {
    if (isLoading) return;
    await onSendMessage('Deliver to Allen Avenue, Ikeja', {
      messageType: 'location',
      location: {
        latitude: 6.6018,
        longitude: 3.3515,
        name: 'Allen Avenue, Ikeja',
        address: 'Ikeja, Lagos',
      },
    });
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
      {/* Left Column: Composable Control Workbench */}
      <div className="lg:col-span-5 space-y-4">
        <SimulatorControlBar
          isBackendConnected={isBackendConnected}
          merchants={merchants}
          activePhoneNumberId={activePhoneNumberId}
          onSelectMerchantPhoneId={onSelectMerchantPhoneId}
          activeProvider={activeProvider}
          onSelectProvider={onSelectProvider}
        />

        <div className="bg-[#151518] border border-white/5 rounded-2xl p-4 shadow-sm">
          <div className="flex items-center justify-between mb-3 pb-2.5 border-b border-white/5">
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => setLeftTab('scenarios')}
                className={`px-2.5 py-1 rounded-lg text-[11px] font-medium transition-colors flex items-center gap-1 ${
                  leftTab === 'scenarios'
                    ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                    : 'text-gray-400 hover:text-white bg-white/5'
                }`}
              >
                <Sparkles className="w-3 h-3" />
                <span>Scenarios</span>
              </button>
              <button
                onClick={() => setLeftTab('chaos')}
                id="tab-chaos-btn"
                className={`px-2.5 py-1 rounded-lg text-[11px] font-medium transition-colors flex items-center gap-1 ${
                  leftTab === 'chaos'
                    ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                    : 'text-gray-400 hover:text-white bg-white/5'
                }`}
              >
                <Flame className="w-3 h-3" />
                <span>Edge Cases & Faults</span>
              </button>
              <button
                onClick={() => setLeftTab('nlu')}
                id="tab-nlu-frame-btn"
                className={`px-2.5 py-1 rounded-lg text-[11px] font-medium transition-colors flex items-center gap-1 ${
                  leftTab === 'nlu'
                    ? 'bg-purple-500/20 text-purple-300 border border-purple-500/30'
                    : 'text-gray-400 hover:text-white bg-white/5'
                }`}
              >
                <Sliders className="w-3 h-3" />
                <span>NLU & Frame</span>
              </button>
              <button
                onClick={() => setLeftTab('telemetry')}
                id="tab-telemetry-btn"
                className={`px-2.5 py-1 rounded-lg text-[11px] font-medium transition-colors flex items-center gap-1 ${
                  leftTab === 'telemetry'
                    ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/30'
                    : 'text-gray-400 hover:text-white bg-white/5'
                }`}
              >
                <Activity className="w-3 h-3" />
                <span>Telemetry</span>
              </button>
            </div>

            <button
              onClick={onResetChat}
              id="reset-chat-btn"
              className="flex items-center gap-1 text-[10px] text-gray-400 hover:text-white transition-colors bg-white/5 hover:bg-white/10 border border-white/5 px-2.5 py-1 rounded-lg uppercase tracking-wider"
            >
              <RotateCcw className="w-3 h-3" />
              <span>Reset</span>
            </button>
          </div>

          {leftTab === 'scenarios' && (
            <ScenarioPresetsPanel
              selectedPreset={selectedPreset}
              onSelectPreset={(id, text) => {
                setSelectedPreset(id);
                setInputText(text);
              }}
            />
          )}

          {leftTab === 'chaos' && (
            <FaultInjectionPanel
              isLoading={isLoading}
              faultProfile={faultProfile}
              windowState={windowState}
              onUpdateFaultProfile={onUpdateFaultProfile}
              onSendBurst={onSendBurst}
              onSendTemplate={onSendTemplate}
            />
          )}

          {leftTab === 'nlu' && (
            <NluFrameInspectorPanel
              nluController={nluController}
              activeFrame={activeFrame}
              onUpdateNluController={onUpdateNluController}
            />
          )}

          {leftTab === 'telemetry' && (
            <TelemetryStreamPanel
              telemetryEvents={telemetryEvents}
              onClearTelemetry={onClearTelemetry}
              jaegerUiUrl={jaegerUiUrl}
            />
          )}
        </div>
      </div>

      {/* Right Column: High-Fidelity WhatsApp Phone Shell */}
      <div className="lg:col-span-7 flex justify-center">
        <div className="w-full max-w-md bg-[#0e0e10] rounded-[40px] p-3 shadow-2xl border border-white/10 ring-1 ring-black">
          <div className="flex justify-center items-center pb-2">
            <div className="h-4 w-28 bg-black/60 rounded-full flex items-center justify-center gap-2 border border-white/5">
              <div className="h-2 w-2 rounded-full bg-zinc-800"></div>
              <div className="h-1.5 w-12 rounded-full bg-zinc-800"></div>
            </div>
          </div>

          <div className="bg-[#0a0a0b] rounded-[32px] overflow-hidden flex flex-col h-[640px] border border-white/5 relative">
            {/* WhatsApp Top Header */}
            <div className="bg-[#151518] px-4 py-3 flex items-center justify-between border-b border-white/5 text-white select-none">
              <div className="flex items-center gap-2.5">
                <div className="relative">
                  <div className="h-9 w-9 rounded-full bg-emerald-500 text-black flex items-center justify-center font-bold text-xs shadow">
                    {currentMerchant.business_name
                      .split(' ')
                      .slice(0, 2)
                      .map((w) => w[0])
                      .join('')}
                  </div>
                  <div className="absolute -bottom-0.5 -right-0.5 h-3.5 w-3.5 rounded-full bg-emerald-500 border-2 border-[#151518] flex items-center justify-center">
                    <Check className="w-2 h-2 text-black stroke-[3]" />
                  </div>
                </div>
                <div>
                  <div className="flex items-center gap-1.5">
                    <span className="font-semibold text-xs text-white truncate max-w-[180px]">
                      {currentMerchant.business_name}
                    </span>
                    <span className="bg-emerald-500/10 text-emerald-400 text-[9px] font-bold px-1.5 py-0.2 rounded-full border border-emerald-500/30">
                      Verified
                    </span>
                  </div>
                  <div className="text-[10px] text-emerald-400 flex items-center gap-1.5">
                    <span
                      className={`h-1.5 w-1.5 rounded-full ${
                        windowState.is_open ? 'bg-emerald-400 animate-pulse' : 'bg-red-400'
                      }`}
                    ></span>
                    <span>
                      {windowState.is_open
                        ? `24h Session Open (${windowState.remaining_hours}h)`
                        : '24h Session Expired (Template Only)'}
                    </span>
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-2 text-gray-300">
                <span className="text-[10px] font-mono bg-white/5 px-2 py-0.5 rounded text-gray-300 border border-white/10">
                  {activeProvider.toUpperCase()}
                </span>
              </div>
            </div>

            {/* WhatsApp Chat Body */}
            <div
              className="flex-1 p-3.5 overflow-y-auto space-y-3 relative"
              style={{
                backgroundImage: `radial-gradient(rgba(255,255,255,0.06) 1px, transparent 1px)`,
                backgroundSize: '16px 16px',
              }}
            >
              <div className="flex justify-center">
                <div className="bg-[#151518] border border-white/5 text-[#ffd279] text-[10px] px-3 py-1.5 rounded-xl text-center max-w-xs shadow-sm flex items-center gap-1.5">
                  <ShieldAlert className="w-3.5 h-3.5 text-[#ffd279] flex-shrink-0" />
                  <span>
                    Messages are NDPA compliant & end-to-end encrypted. BVN & NIN are auto-scrubbed.
                  </span>
                </div>
              </div>

              {messages.map((msg) => (
                <PhoneChatBubble
                  key={msg.id}
                  message={msg}
                  isLoading={isLoading}
                  remainingHoldSeconds={remainingHoldSeconds}
                  onInteractiveTap={handleInteractiveTap}
                  onOpenListDrawer={setOpenListDrawer}
                  onSimulateBankTransfer={onSimulateBankTransfer}
                />
              ))}

              {isLoading && (
                <div className="flex items-center gap-1 bg-[#151518] text-gray-300 px-3 py-2 rounded-xl max-w-[120px] shadow border border-white/5">
                  <span className="h-1.5 w-1.5 rounded-full bg-gray-400 animate-bounce"></span>
                  <span className="h-1.5 w-1.5 rounded-full bg-gray-400 animate-bounce [animation-delay:0.2s]"></span>
                  <span className="h-1.5 w-1.5 rounded-full bg-gray-400 animate-bounce [animation-delay:0.4s]"></span>
                  <span className="text-[10px] text-gray-400 ml-1">Typing...</span>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            <InteractiveListDrawer
              drawer={openListDrawer}
              onClose={() => setOpenListDrawer(null)}
              onSelectRow={(id, title) => handleInteractiveTap(id, title, 'list_reply')}
            />

            {/* WhatsApp Input Footer */}
            <div className="bg-[#151518] p-2.5 border-t border-white/5 flex items-center gap-1.5">
              <button
                type="button"
                onClick={handleSendVoiceNote}
                disabled={isLoading}
                title="Send Voice Note (Tests ADR-0037 Voice Note Passthrough)"
                id="whatsapp-voice-note-btn"
                className="p-1.5 rounded-lg text-gray-400 hover:text-emerald-400 hover:bg-white/5 transition-colors"
              >
                <Mic className="w-4 h-4" />
              </button>
              <button
                type="button"
                onClick={handleShareLocation}
                disabled={isLoading}
                title="Share Delivery Location Pin"
                id="whatsapp-location-btn"
                className="p-1.5 rounded-lg text-gray-400 hover:text-emerald-400 hover:bg-white/5 transition-colors"
              >
                <MapPin className="w-4 h-4" />
              </button>

              <form onSubmit={handleSend} className="flex-1 flex items-center">
                <input
                  type="text"
                  id="whatsapp-chat-input"
                  value={inputText}
                  onChange={(e) => setInputText(e.target.value)}
                  placeholder="Type in Pidgin, English, or slang..."
                  className="w-full bg-[#0e0e10] text-gray-100 placeholder-gray-500 text-xs px-3 py-2 rounded-xl focus:outline-none focus:ring-1 focus:ring-emerald-500 border border-white/5"
                />
              </form>

              <button
                id="whatsapp-send-btn"
                onClick={() => handleSend()}
                disabled={!inputText.trim() || isLoading}
                className="h-8 w-8 rounded-full bg-emerald-500 hover:bg-emerald-400 disabled:opacity-40 text-black flex items-center justify-center shadow transition-colors"
              >
                <Send className="w-3.5 h-3.5 ml-0.5" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
