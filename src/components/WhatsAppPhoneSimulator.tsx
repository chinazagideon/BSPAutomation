import React, { useState, useEffect, useRef } from 'react';
import { 
  Send, 
  CheckCheck, 
  Clock, 
  ShieldAlert, 
  Sparkles, 
  Zap, 
  CreditCard, 
  FileText, 
  PhoneCall, 
  ChevronRight, 
  RotateCcw,
  CheckCircle2,
  AlertTriangle,
  Building2,
  Mic,
  Smile,
  Paperclip,
  ArrowDownLeft,
  Copy,
  Check
} from 'lucide-react';
import { ChatMessage, LeadScore } from '../types';

interface WhatsAppPhoneSimulatorProps {
  messages: ChatMessage[];
  onSendMessage: (text: string) => Promise<void>;
  isLoading: boolean;
  onSimulateBankTransfer: (ref: string, amount: number) => void;
  activeHoldExpiry?: string;
  onResetChat: () => void;
}

export const WhatsAppPhoneSimulator: React.FC<WhatsAppPhoneSimulatorProps> = ({
  messages,
  onSendMessage,
  isLoading,
  onSimulateBankTransfer,
  activeHoldExpiry,
  onResetChat,
}) => {
  const [inputText, setInputText] = useState('');
  const [copiedAccount, setCopiedAccount] = useState(false);
  const [remainingHoldSeconds, setRemainingHoldSeconds] = useState(600); // 10 minutes default
  const [selectedPreset, setSelectedPreset] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  // 10-minute hold countdown timer
  useEffect(() => {
    const timer = setInterval(() => {
      setRemainingHoldSeconds((prev) => (prev > 0 ? prev - 1 : 0));
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  const formatCountdown = (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s < 10 ? '0' : ''}${s}`;
  };

  const handleSend = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!inputText.trim() || isLoading) return;
    const textToSend = inputText;
    setInputText('');
    await onSendMessage(textToSend);
  };

  const presets = [
    {
      id: 'pidgin-order',
      title: '🇳🇬 Pidgin Wholesale Order',
      text: 'How far! I wan order 3 cartons of vegetable oil make una deliver to Allen Avenue, Ikeja.',
      description: 'Tests fast-path Nigerian Pidgin intent + 10m anti-ghosting checkout hold.',
    },
    {
      id: 'bvn-sanitization',
      title: '🛡️ PII BVN/NIN Redaction',
      text: 'Good day, please verify my business account. My BVN is 22298765432 and my account number is 0123456789 (Access Bank).',
      description: 'Tests NDPA pre-processing regex scrubbing before routing to LLM.',
    },
    {
      id: 'transfer-proof',
      title: '💳 Debit Alert Confirmation',
      text: 'I don transfer ₦73,500 to the Moniepoint account. Check your alert, receipt is attached.',
      description: 'Triggers instant double-entry ledger reconciliation and receipt push.',
    },
    {
      id: 'atomic-reservation',
      title: '🗓️ GiST Atomic Slot Booking',
      text: 'I want to reserve a 1-on-1 CRM onboarding session for tomorrow 2:00 PM in Ikeja.',
      description: 'Tests PostgreSQL exclusion constraint slot locking without double booking.',
    },
    {
      id: 'agent-escalation',
      title: '👨‍💼 Resilient Agent Handoff',
      text: 'I have a complex logistics API question for our nationwide fleet. Talk to human agent abeg.',
      description: 'Generates AI context injection card and checks agent heartbeat status.',
    },
  ];

  const handleCopyAccount = (acct: string) => {
    navigator.clipboard.writeText(acct);
    setCopiedAccount(true);
    setTimeout(() => setCopiedAccount(false), 2000);
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
      {/* Left Column: Preset Test Scenarios & Explainer */}
      <div className="lg:col-span-5 space-y-4">
        <div className="bg-[#151518] border border-white/5 rounded-2xl p-4 shadow-sm">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-emerald-400" />
              <h2 className="text-xs font-semibold text-gray-300 uppercase tracking-widest">Test Scenarios (SME Workflows)</h2>
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
          <p className="text-xs text-gray-400 mb-3 leading-relaxed">
            Click any scenario to simulate real Nigerian SME WhatsApp interactions with instant fast-path NLP, PII redaction, and decoupled webhook handling.
          </p>

          <div className="space-y-2">
            {presets.map((preset) => (
              <button
                key={preset.id}
                id={`preset-${preset.id}`}
                onClick={() => {
                  setInputText(preset.text);
                  setSelectedPreset(preset.id);
                }}
                className={`w-full text-left p-3 rounded-xl border text-xs transition-all duration-150 ${
                  selectedPreset === preset.id
                    ? 'border-emerald-500/50 bg-emerald-500/10 text-emerald-300 ring-1 ring-emerald-500/30'
                    : 'border-white/5 bg-white/[0.02] text-gray-300 hover:border-white/10 hover:bg-white/5'
                }`}
              >
                <div className="flex items-center justify-between font-medium mb-1">
                  <span className="text-gray-200">{preset.title}</span>
                  <ChevronRight className="w-3.5 h-3.5 text-gray-500" />
                </div>
                <div className="text-gray-400 text-[11px] line-clamp-1 italic mb-1">"{preset.text}"</div>
                <div className="text-[10px] text-emerald-400 font-mono">{preset.description}</div>
              </button>
            ))}
          </div>
        </div>

        {/* Live Architecture Insights Card */}
        <div className="bg-[#151518] border border-white/5 rounded-2xl p-4 space-y-3 shadow-sm">
          <h3 className="text-xs font-semibold text-gray-300 uppercase tracking-widest flex items-center gap-2">
            <Zap className="w-3.5 h-3.5 text-amber-400" />
            <span>Infrastructure Protection Specs</span>
          </h3>
          <div className="space-y-2 text-xs">
            <div className="flex items-center justify-between p-2.5 rounded-xl bg-[#0e0e10] border border-white/5">
              <span className="text-gray-400">Meta Webhook Decoupling</span>
              <span className="text-emerald-400 font-mono font-medium text-[11px]">&lt; 25ms 200 OK</span>
            </div>
            <div className="flex items-center justify-between p-2.5 rounded-xl bg-[#0e0e10] border border-white/5">
              <span className="text-gray-400">Anti-Ghosting Hold Window</span>
              <span className="text-amber-400 font-mono font-medium text-[11px]">10 Minutes Timer</span>
            </div>
            <div className="flex items-center justify-between p-2.5 rounded-xl bg-[#0e0e10] border border-white/5">
              <span className="text-gray-400">NDPA PII Pre-Scrubbing</span>
              <span className="text-blue-400 font-mono font-medium text-[11px]">BVN / NIN / NUBAN</span>
            </div>
            <div className="flex items-center justify-between p-2.5 rounded-xl bg-[#0e0e10] border border-white/5">
              <span className="text-gray-400">Double-Booking Prevention</span>
              <span className="text-purple-400 font-mono font-medium text-[11px]">GiST [TSTZRANGE] Lock</span>
            </div>
          </div>
        </div>
      </div>

      {/* Right Column: High-Fidelity WhatsApp Phone Shell */}
      <div className="lg:col-span-7 flex justify-center">
        <div className="w-full max-w-md bg-[#0e0e10] rounded-[40px] p-3 shadow-2xl border border-white/10 ring-1 ring-black">
          {/* Phone Top Speaker & Camera Notch */}
          <div className="flex justify-center items-center pb-2">
            <div className="h-4 w-28 bg-black/60 rounded-full flex items-center justify-center gap-2 border border-white/5">
              <div className="h-2 w-2 rounded-full bg-zinc-800"></div>
              <div className="h-1.5 w-12 rounded-full bg-zinc-800"></div>
            </div>
          </div>

          {/* WhatsApp Inner Screen Container */}
          <div className="bg-[#0a0a0b] rounded-[32px] overflow-hidden flex flex-col h-[640px] border border-white/5">
            {/* WhatsApp Green Top Header */}
            <div className="bg-[#151518] px-4 py-3 flex items-center justify-between border-b border-white/5 text-white select-none">
              <div className="flex items-center gap-2.5">
                <div className="relative">
                  <div className="h-9 w-9 rounded-full bg-emerald-500 text-black flex items-center justify-center font-bold text-sm shadow">
                    KF
                  </div>
                  <div className="absolute -bottom-0.5 -right-0.5 h-3.5 w-3.5 rounded-full bg-emerald-500 border-2 border-[#151518] flex items-center justify-center">
                    <Check className="w-2 h-2 text-black stroke-[3]" />
                  </div>
                </div>
                <div>
                  <div className="flex items-center gap-1.5">
                    <span className="font-semibold text-xs text-white">KudiFlow Store Nigeria</span>
                    <span className="bg-emerald-500/10 text-emerald-400 text-[9px] font-bold px-1.5 py-0.2 rounded-full border border-emerald-500/30">
                      Verified
                    </span>
                  </div>
                  <div className="text-[10px] text-emerald-400 flex items-center gap-1">
                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                    <span>Online (Anti-Ghosting Protected)</span>
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-2 text-gray-300">
                <span className="text-[10px] font-mono bg-white/5 px-2 py-0.5 rounded text-gray-300 border border-white/10">
                  +234 800 KUDI
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
              {/* WhatsApp Security Banner */}
              <div className="flex justify-center">
                <div className="bg-[#151518] border border-white/5 text-[#ffd279] text-[10px] px-3 py-1.5 rounded-xl text-center max-w-xs shadow-sm flex items-center gap-1.5">
                  <ShieldAlert className="w-3.5 h-3.5 text-[#ffd279] flex-shrink-0" />
                  <span>Messages are NDPA compliant & end-to-end encrypted. BVN & NIN are auto-scrubbed.</span>
                </div>
              </div>

              {/* Chat Message List */}
              {messages.map((msg) => {
                const isUser = msg.sender === 'user';
                return (
                  <div
                    key={msg.id}
                    className={`flex flex-col ${isUser ? 'items-end' : 'items-start'} transition-all`}
                  >
                    <div
                      className={`max-w-[85%] rounded-2xl p-3 text-xs shadow-md relative ${
                        isUser
                          ? 'bg-emerald-600 text-white rounded-tr-none'
                          : 'bg-[#151518] text-gray-100 rounded-tl-none border border-white/5'
                      }`}
                    >
                      {/* Message Content with Markdown linebreaks */}
                      <div className="whitespace-pre-line leading-relaxed">{msg.text}</div>

                      {/* Interactive Payment / Anti-Ghosting Card */}
                      {msg.interactiveType === 'payment_link' && msg.metadata && (
                        <div className="mt-2.5 pt-2.5 border-t border-white/10 bg-black/40 -mx-1 p-2.5 rounded-xl space-y-2">
                          <div className="flex items-center justify-between text-[11px]">
                            <span className="text-amber-300 font-semibold flex items-center gap-1">
                              <Clock className="w-3.5 h-3.5 animate-spin" />
                              Anti-Ghosting Hold:
                            </span>
                            <span className="font-mono bg-amber-500/20 text-amber-300 px-2 py-0.5 rounded font-bold text-[10px]">
                              {formatCountdown(remainingHoldSeconds)} remaining
                            </span>
                          </div>

                          <div className="bg-[#0e0e10] p-2.5 rounded-lg border border-white/5 space-y-1.5 text-[11px]">
                            <div className="flex justify-between text-gray-400">
                              <span>Dedicated Virtual Bank:</span>
                              <span className="text-white font-medium">{msg.metadata.bankName || 'Moniepoint MFB'}</span>
                            </div>
                            <div className="flex justify-between items-center text-gray-400">
                              <span>Account Number:</span>
                              <div className="flex items-center gap-1.5">
                                <span className="text-emerald-400 font-mono font-bold">{msg.metadata.accountNumber || '9031842901'}</span>
                                <button
                                  onClick={() => handleCopyAccount(msg.metadata?.accountNumber || '9031842901')}
                                  className="text-gray-400 hover:text-white"
                                  title="Copy account"
                                >
                                  {copiedAccount ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                                </button>
                              </div>
                            </div>
                            <div className="flex justify-between text-gray-400">
                              <span>Total Amount:</span>
                              <span className="text-white font-bold">₦{(msg.metadata.amountNaira || 73500).toLocaleString()}</span>
                            </div>
                          </div>

                          {/* Instant Transfer Trigger Button */}
                          <button
                            id="simulate-transfer-btn"
                            onClick={() => onSimulateBankTransfer('NIBSS_PAY_' + Math.floor(Math.random() * 90000 + 10000), msg.metadata?.amountNaira || 73500)}
                            className="w-full bg-emerald-500 hover:bg-emerald-400 text-black font-bold uppercase tracking-widest py-2 px-3 rounded-lg text-[10px] flex items-center justify-center gap-1.5 shadow transition-colors"
                          >
                            <CreditCard className="w-3.5 h-3.5" />
                            <span>Simulate Customer Bank Transfer</span>
                          </button>
                        </div>
                      )}

                      {/* Timestamp & Delivery status ticks */}
                      <div className="flex items-center justify-end gap-1 mt-1 text-[9px] text-gray-400">
                        <span>{msg.timestamp}</span>
                        {isUser && <CheckCheck className="w-3 h-3 text-[#53bdeb]" />}
                      </div>
                    </div>

                    {/* Metadata tags (Intent / Fast Path / PII Clean) */}
                    {msg.metadata && !isUser && (
                      <div className="flex items-center gap-1.5 mt-1 ml-1 text-[9px]">
                        {msg.metadata.isFastPath ? (
                          <span className="bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 px-1.5 py-0.2 rounded font-mono flex items-center gap-0.5">
                            <Zap className="w-2.5 h-2.5" /> Fast-Path (0 Tokens)
                          </span>
                        ) : (
                          <span className="bg-purple-500/10 border border-purple-500/30 text-purple-300 px-1.5 py-0.2 rounded font-mono flex items-center gap-0.5">
                            <Sparkles className="w-2.5 h-2.5" /> Gemini 3.7 Flash
                          </span>
                        )}
                        {msg.metadata.leadTier && (
                          <span className={`px-1.5 py-0.2 rounded font-mono font-bold ${
                            msg.metadata.leadTier === 'HOT' ? 'bg-red-500/10 text-red-400 border border-red-500/30' : 'bg-amber-500/10 text-amber-400 border border-amber-500/30'
                          }`}>
                            {msg.metadata.leadTier} LEAD
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}

              {/* Typing indicator */}
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

            {/* WhatsApp Input Footer */}
            <div className="bg-[#151518] p-3 border-t border-white/5 flex items-center gap-2">
              <div className="flex items-center gap-1.5 text-gray-400">
                <Smile className="w-4 h-4 hover:text-white cursor-pointer" />
                <Paperclip className="w-4 h-4 hover:text-white cursor-pointer" />
              </div>

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
