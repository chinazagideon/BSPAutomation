import React, { useState } from 'react';
import {
  Activity,
  Check,
  CheckCheck,
  Clock,
  Copy,
  CreditCard,
  Layers,
  ListFilter,
  Sparkles,
  Zap,
} from 'lucide-react';
import { APP_CONFIG } from '../../config/env';
import { ChatMessage, InteractiveListSection } from '../../types';

interface PhoneChatBubbleProps {
  message: ChatMessage;
  isLoading: boolean;
  remainingHoldSeconds: number;
  onInteractiveTap: (id: string, title: string, type: 'button_reply' | 'list_reply') => void;
  onOpenListDrawer: (drawer: { title: string; sections: InteractiveListSection[] }) => void;
  onSimulateBankTransfer: (ref: string, amount: number) => void;
}

export const PhoneChatBubble: React.FC<PhoneChatBubbleProps> = ({
  message: msg,
  isLoading,
  remainingHoldSeconds,
  onInteractiveTap,
  onOpenListDrawer,
  onSimulateBankTransfer,
}) => {
  const [copiedAccount, setCopiedAccount] = useState(false);

  const isUser = msg.sender === 'user';
  const isSystem = msg.sender === 'system' || msg.interactiveType === 'system_alert';

  const formatCountdown = (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s < 10 ? '0' : ''}${s}`;
  };

  const handleCopyAccount = (acct: string) => {
    navigator.clipboard.writeText(acct);
    setCopiedAccount(true);
    setTimeout(() => setCopiedAccount(false), 2000);
  };

  if (isSystem) {
    return (
      <div className="flex justify-center my-2">
        <div className="bg-red-950/60 border border-red-500/40 text-red-200 text-[10px] px-3 py-2 rounded-xl max-w-[90%] font-mono leading-relaxed shadow">
          {msg.text}
        </div>
      </div>
    );
  }

  return (
    <div className={`flex flex-col ${isUser ? 'items-end' : 'items-start'} transition-all`}>
      <div
        className={`max-w-[85%] rounded-2xl p-3 text-xs shadow-md relative ${
          isUser
            ? 'bg-emerald-600 text-white rounded-tr-none'
            : 'bg-[#151518] text-gray-100 rounded-tl-none border border-white/5'
        }`}
      >
        {msg.headerText && (
          <div className="font-bold text-[11px] text-emerald-400 mb-1 pb-1 border-b border-white/10">
            {msg.headerText}
          </div>
        )}

        <div className="whitespace-pre-line leading-relaxed">{msg.text}</div>

        {/* 1. Interactive 3-Button Reply Card (ADR-0046) */}
        {msg.buttons && msg.buttons.length > 0 && (
          <div className="mt-2.5 pt-2 border-t border-white/10 space-y-1.5">
            {msg.buttons.map((btn) => (
              <button
                key={btn.id}
                onClick={() => onInteractiveTap(btn.id, btn.title, 'button_reply')}
                disabled={isLoading}
                className="w-full py-2 px-3 rounded-xl bg-[#0e0e10] hover:bg-emerald-500/20 border border-emerald-500/30 text-emerald-400 font-semibold text-[11px] flex items-center justify-center gap-1.5 transition-colors"
              >
                <span>{btn.title}</span>
              </button>
            ))}
          </div>
        )}

        {/* 2. Interactive List Picker Trigger Button (ADR-0046) */}
        {msg.listSections && msg.listSections.length > 0 && (
          <div className="mt-2.5 pt-2 border-t border-white/10">
            <button
              onClick={() =>
                onOpenListDrawer({
                  title: msg.headerText || msg.buttonTitle || 'Select an Option',
                  sections: msg.listSections || [],
                })
              }
              className="w-full py-2 px-3 rounded-xl bg-[#0e0e10] hover:bg-emerald-500/20 border border-emerald-500/30 text-emerald-400 font-semibold text-[11px] flex items-center justify-center gap-1.5 transition-colors"
            >
              <ListFilter className="w-3.5 h-3.5" />
              <span>{msg.buttonTitle || 'View Options'}</span>
            </button>
          </div>
        )}

        {/* 3. Interactive Carousel Cards */}
        {msg.carouselCards && msg.carouselCards.length > 0 && (
          <div className="mt-2.5 pt-2 border-t border-white/10 flex gap-2 overflow-x-auto pb-1">
            {msg.carouselCards.map((card, i) => (
              <div
                key={i}
                className="min-w-[180px] bg-[#0e0e10] rounded-xl p-2 border border-white/10 flex flex-col justify-between"
              >
                <div className="text-[11px] text-gray-200 mb-2">{card.body_text}</div>
                <a
                  href={card.cta_url}
                  target="_blank"
                  rel="noreferrer"
                  className="block text-center py-1 px-2 rounded-lg bg-emerald-500/20 text-emerald-300 text-[10px] font-semibold"
                >
                  {card.cta_text}
                </a>
              </div>
            ))}
          </div>
        )}

        {/* 4. Interactive Payment / Anti-Ghosting Card */}
        {msg.interactiveType === 'payment_link' && (
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
                <span className="text-white font-medium">
                  {msg.metadata?.bankName || APP_CONFIG.DEFAULT_VIRTUAL_BANK}
                </span>
              </div>
              <div className="flex justify-between items-center text-gray-400">
                <span>Account Number:</span>
                <div className="flex items-center gap-1.5">
                  <span className="text-emerald-400 font-mono font-bold">
                    {msg.metadata?.accountNumber || APP_CONFIG.DEFAULT_VIRTUAL_ACCOUNT}
                  </span>
                  <button
                    onClick={() =>
                      handleCopyAccount(
                        msg.metadata?.accountNumber || APP_CONFIG.DEFAULT_VIRTUAL_ACCOUNT
                      )
                    }
                    className="text-gray-400 hover:text-white"
                    title="Copy account"
                  >
                    {copiedAccount ? (
                      <Check className="w-3 h-3 text-emerald-400" />
                    ) : (
                      <Copy className="w-3 h-3" />
                    )}
                  </button>
                </div>
              </div>
            </div>

            <button
              id="simulate-transfer-btn"
              onClick={() =>
                onSimulateBankTransfer(
                  'NIBSS_PAY_' + Math.floor(Math.random() * 90000 + 10000),
                  msg.metadata?.amountNaira || 78000
                )
              }
              className="w-full bg-emerald-500 hover:bg-emerald-400 text-black font-bold uppercase tracking-widest py-2 px-3 rounded-lg text-[10px] flex items-center justify-center gap-1.5 shadow transition-colors"
            >
              <CreditCard className="w-3.5 h-3.5" />
              <span>Simulate Customer Bank Transfer</span>
            </button>
          </div>
        )}

        <div className="flex items-center justify-end gap-1 mt-1 text-[9px] text-gray-400">
          <span>{msg.timestamp}</span>
          {msg.status === 'failed' ? (
            <span className="text-red-400 font-bold">! Failed</span>
          ) : (
            isUser && <CheckCheck className="w-3 h-3 text-[#53bdeb]" />
          )}
        </div>
      </div>

      {/* Metadata tags (Routing Source / Intent / Lead Tier) */}
      {msg.metadata && !isUser && (
        <div className="flex flex-wrap items-center gap-1.5 mt-1 ml-1 text-[9px]">
          {msg.metadata.routingSource === 'NEGOTIATION_FRAME' ? (
            <span className="bg-blue-500/10 border border-blue-500/30 text-blue-300 px-1.5 py-0.2 rounded font-mono flex items-center gap-0.5">
              <Layers className="w-2.5 h-2.5" /> Slot Frame (0 Tokens)
            </span>
          ) : msg.metadata.isFastPath || msg.metadata.routingSource === 'FAST_PATH' ? (
            <span className="bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 px-1.5 py-0.2 rounded font-mono flex items-center gap-0.5">
              <Zap className="w-2.5 h-2.5" /> Stage 1 Fast-Path
            </span>
          ) : msg.metadata.routingSource === 'CUSTOM_LOCAL_MODEL' ? (
            <span className="bg-cyan-500/10 border border-cyan-500/30 text-cyan-300 px-1.5 py-0.2 rounded font-mono flex items-center gap-0.5">
              <Activity className="w-2.5 h-2.5" /> Stage 2 ONNX Model
            </span>
          ) : (
            <span className="bg-purple-500/10 border border-purple-500/30 text-purple-300 px-1.5 py-0.2 rounded font-mono flex items-center gap-0.5">
              <Sparkles className="w-2.5 h-2.5" /> Stage 3 LLM
            </span>
          )}
          {msg.metadata.intent && (
            <span className="bg-white/5 border border-white/10 text-gray-300 px-1.5 py-0.2 rounded font-mono">
              {msg.metadata.intent}
            </span>
          )}
          {msg.metadata.leadTier && (
            <span
              className={`px-1.5 py-0.2 rounded font-mono font-bold ${
                msg.metadata.leadTier === 'HOT'
                  ? 'bg-red-500/10 text-red-400 border border-red-500/30'
                  : 'bg-amber-500/10 text-amber-400 border border-amber-500/30'
              }`}
            >
              {msg.metadata.leadTier}
            </span>
          )}
        </div>
      )}
    </div>
  );
};
