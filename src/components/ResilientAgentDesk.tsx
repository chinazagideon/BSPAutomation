import React, { useState } from 'react';
import { 
  Users, 
  Wifi, 
  WifiOff, 
  Zap, 
  ZapOff, 
  Sparkles, 
  MessageSquare, 
  CheckCircle2, 
  AlertTriangle, 
  Clock, 
  Building2, 
  ArrowRight,
  ShieldCheck,
  Send,
  RefreshCw
} from 'lucide-react';
import { AgentProfile } from '../types';

interface ResilientAgentDeskProps {
  agents: AgentProfile[];
  onToggleAgentStatus: (agentId: string) => void;
  onGenerateContextInjection: (customerName: string, phone: string) => Promise<any>;
}

export const ResilientAgentDesk: React.FC<ResilientAgentDeskProps> = ({
  agents,
  onToggleAgentStatus,
  onGenerateContextInjection,
}) => {
  const [selectedCustomer, setSelectedCustomer] = useState({
    name: 'Chidinma Okafor (Lekki Boutique)',
    phone: '+2348023456789',
    history: [
      { sender: 'user', text: 'How far! I need 10 cartons of sunflower oil delivered to Lekki Phase 1 today.' },
      { sender: 'bot', text: 'Hello Chidinma! The wholesale price for 10 cartons is ₦220,000 including priority dispatch.' },
      { sender: 'user', text: 'Can I pay on delivery for first-time orders? Or speak to your sales manager.' },
    ],
  });

  const [contextCard, setContextCard] = useState<any>({
    executiveSummary: 'Customer wants to buy 10 cartons of sunflower oil for Lekki Phase 1. Negotiating pay-on-delivery terms for first-time wholesale order.',
    detectedBudget: '₦220,000',
    urgencyTier: 'HOT',
    piiScrubbed: true,
    suggestedNextGreeting: 'Good day Chidinma, I see you are looking for 10 cartons of sunflower oil in Lekki! I can offer a 50% commitment deposit with balance on arrival.',
    keyBlockers: 'Payment terms trust verification for new wholesale account.',
  });

  const [isSynthesizing, setIsSynthesizing] = useState(false);
  const [replyInput, setReplyInput] = useState(contextCard.suggestedNextGreeting);

  const handleGenerateContext = async () => {
    setIsSynthesizing(true);
    try {
      const res = await onGenerateContextInjection(selectedCustomer.name, selectedCustomer.phone);
      if (res && res.summary) {
        setContextCard(res.summary);
        setReplyInput(res.summary.suggestedNextGreeting || '');
      }
    } catch (e) {
      console.error('Context generation error:', e);
    } finally {
      setIsSynthesizing(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="bg-[#151518] border border-white/5 rounded-2xl p-5 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="h-2 w-2 rounded-full bg-emerald-500"></span>
              <h2 className="text-sm font-semibold text-white tracking-tight">Resilient "No-Repeat" Human Handoff Desk</h2>
            </div>
            <p className="text-xs text-gray-400 max-w-3xl leading-relaxed">
              Nigerian support teams face frequent power (NEPA) outages and fiber drops. 
              Our heartbeat monitor detects agent drops within 5 seconds, reroutes tickets asynchronously to backup hubs, and injects <strong className="text-purple-400 font-mono">Gemini-generated context cards</strong> so agents never ask repeated questions.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <div className="bg-[#0e0e10] border border-white/5 px-4 py-2 rounded-xl text-center">
              <div className="text-[10px] text-gray-500 uppercase tracking-widest font-mono">Failover Latency</div>
              <div className="text-base font-bold text-emerald-400 font-mono mt-0.5">&lt; 5s</div>
            </div>
            <div className="bg-[#0e0e10] border border-white/5 px-4 py-2 rounded-xl text-center">
              <div className="text-[10px] text-gray-500 uppercase tracking-widest font-mono">Context Repetition</div>
              <div className="text-base font-bold text-blue-400 font-mono mt-0.5">0% (Eliminated)</div>
            </div>
          </div>
        </div>
      </div>

      {/* Grid: Agent Heartbeat Monitor & Context Injection Workspace */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: Agent Heartbeat & Power Status */}
        <div className="lg:col-span-5 space-y-4">
          <div className="bg-[#151518] border border-white/5 rounded-2xl p-4 shadow-sm">
            <div className="flex items-center justify-between pb-3 border-b border-white/5 mb-3">
              <div className="flex items-center gap-2">
                <Users className="w-4 h-4 text-emerald-400" />
                <h3 className="text-xs font-semibold text-gray-300 uppercase tracking-widest">Live Agent Heartbeat Monitor</h3>
              </div>
              <span className="text-[10px] bg-white/5 text-gray-400 px-2 py-0.5 rounded font-mono border border-white/10">
                {agents.filter(a => a.status === 'ONLINE').length} / {agents.length} Hubs Online
              </span>
            </div>

            <div className="space-y-3">
              {agents.map((agent) => {
                const isOnline = agent.status === 'ONLINE';
                const isNepaOffline = agent.status === 'OFFLINE_NEPA';

                return (
                  <div
                    key={agent.id}
                    id={`agent-card-${agent.id}`}
                    className={`p-3.5 rounded-xl border text-xs space-y-2.5 transition-all ${
                      isOnline
                        ? 'bg-[#0e0e10] border-white/5'
                        : 'bg-red-500/5 border-red-500/30'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <div>
                        <div className="font-semibold text-white flex items-center gap-1.5">
                          <span>{agent.name}</span>
                          {isOnline ? (
                            <span className="h-2 w-2 rounded-full bg-emerald-500"></span>
                          ) : (
                            <span className="h-2 w-2 rounded-full bg-red-400 animate-ping"></span>
                          )}
                        </div>
                        <div className="text-[10px] text-gray-500 flex items-center gap-1 mt-0.5">
                          <Building2 className="w-3 h-3 text-gray-500" />
                          <span>{agent.hub}</span>
                        </div>
                      </div>

                      <button
                        onClick={() => onToggleAgentStatus(agent.id)}
                        className={`text-[10px] font-mono font-bold px-2 py-1 rounded-lg flex items-center gap-1 border transition-colors ${
                          isOnline
                            ? 'bg-red-500/10 border-red-500/30 text-red-300 hover:bg-red-500/20'
                            : 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300 hover:bg-emerald-500/20'
                        }`}
                      >
                        {isOnline ? (
                          <>
                            <ZapOff className="w-3 h-3" />
                            <span>Simulate NEPA Drop</span>
                          </>
                        ) : (
                          <>
                            <Zap className="w-3 h-3" />
                            <span>Restore Power</span>
                          </>
                        )}
                      </button>
                    </div>

                    <div className="grid grid-cols-2 gap-2 text-[11px] p-2.5 rounded-lg bg-[#151518] border border-white/5">
                      <div>
                        <span className="text-[10px] text-gray-500 uppercase tracking-widest">Active Queue:</span>
                        <div className="font-medium text-gray-200 mt-0.5">{agent.activeChatsCount} chats</div>
                      </div>
                      <div>
                        <span className="text-[10px] text-gray-500 uppercase tracking-widest">Last Heartbeat:</span>
                        <div className={`font-mono font-medium mt-0.5 ${isOnline ? 'text-emerald-400' : 'text-red-400'}`}>
                          {agent.lastHeartbeat}
                        </div>
                      </div>
                    </div>

                    {isNepaOffline && (
                      <div className="p-2 rounded-lg bg-red-500/10 border border-red-500/20 text-[10px] text-red-200 flex items-center justify-between">
                        <span>⚡ Power outage detected. Failover queue active.</span>
                        <span className="font-mono text-amber-300">Rerouted to Lekki Hub</span>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Right: AI-Generated Context Injection Card */}
        <div className="lg:col-span-7 space-y-4">
          <div className="bg-[#151518] border border-white/5 rounded-2xl p-4 shadow-sm">
            <div className="flex items-center justify-between pb-3 border-b border-white/5 mb-3">
              <div className="flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-purple-400" />
                <h3 className="text-xs font-semibold text-gray-300 uppercase tracking-widest">
                  AI-Synthesized Context Injection Card
                </h3>
              </div>
              <button
                onClick={handleGenerateContext}
                disabled={isSynthesizing}
                className="flex items-center gap-1 text-[10px] font-bold uppercase tracking-widest bg-purple-500/10 hover:bg-purple-500/20 border border-purple-500/30 text-purple-300 px-2.5 py-1 rounded-lg transition-colors"
              >
                {isSynthesizing ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Sparkles className="w-3 h-3" />}
                <span>Regenerate Summary</span>
              </button>
            </div>

            {/* Context Card Details */}
            <div className="space-y-3">
              {/* Customer Profile Bar */}
              <div className="p-3.5 rounded-xl bg-[#0e0e10] border border-white/5 flex items-center justify-between text-xs">
                <div>
                  <div className="font-semibold text-white">{selectedCustomer.name}</div>
                  <div className="text-[10px] text-gray-500 font-mono mt-0.5">{selectedCustomer.phone}</div>
                </div>
                <div className="flex items-center gap-2">
                  <span className="bg-red-500/10 text-red-400 border border-red-500/30 text-[10px] font-bold px-2 py-0.5 rounded-full font-mono">
                    HOT LEAD
                  </span>
                  <span className="bg-blue-500/10 text-blue-400 border border-blue-500/30 text-[10px] px-2 py-0.5 rounded-full font-mono flex items-center gap-1">
                    <ShieldCheck className="w-3 h-3" /> PII Scrubbed
                  </span>
                </div>
              </div>

              {/* Core Executive Summary */}
              <div className="p-3.5 rounded-xl bg-purple-500/5 border border-purple-500/20 text-xs space-y-2">
                <div className="text-[10px] uppercase font-bold tracking-widest text-purple-300">Customer Intent Summary:</div>
                <p className="text-gray-200 leading-relaxed font-normal">
                  {contextCard.executiveSummary}
                </p>

                <div className="grid grid-cols-2 gap-2 pt-2 border-t border-purple-500/20 text-[11px]">
                  <div>
                    <span className="text-[10px] text-purple-300/70 uppercase tracking-widest">Estimated Deal Budget:</span>
                    <div className="font-bold text-emerald-400 mt-0.5">{contextCard.detectedBudget}</div>
                  </div>
                  <div>
                    <span className="text-[10px] text-purple-300/70 uppercase tracking-widest">Primary Customer Blocker:</span>
                    <div className="font-medium text-gray-200 mt-0.5">{contextCard.keyBlockers}</div>
                  </div>
                </div>
              </div>

              {/* Recommended Next Greeting / Response */}
              <div className="p-3.5 rounded-xl bg-[#0e0e10] border border-white/5 space-y-2">
                <div className="text-[10px] text-gray-400 uppercase tracking-widest font-bold flex items-center justify-between">
                  <span>AI-Recommended Seamless Reply (Zero Repetition):</span>
                  <span className="text-emerald-400 text-[10px] font-mono">Natural Nigerian Business Tone</span>
                </div>

                <textarea
                  value={replyInput}
                  onChange={(e) => setReplyInput(e.target.value)}
                  rows={3}
                  className="w-full bg-[#151518] border border-white/5 text-xs p-3 rounded-xl text-gray-200 focus:outline-none focus:border-emerald-500"
                />

                <button
                  onClick={() => alert(`Injected response sent to WhatsApp: "${replyInput}"`)}
                  className="w-full bg-emerald-500 hover:bg-emerald-400 text-black font-bold uppercase tracking-widest py-2.5 px-4 rounded-xl text-[11px] flex items-center justify-center gap-1.5 transition-colors shadow-sm"
                >
                  <Send className="w-3.5 h-3.5" />
                  <span>Send Context-Aware Reply to Customer</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
