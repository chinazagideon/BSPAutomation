import React, { useState } from 'react';
import { Header } from './components/Header';
import { WhatsAppPhoneSimulator } from './components/WhatsAppPhoneSimulator';
import { WebhookInspector } from './components/WebhookInspector';
import { NluIntentMatrix } from './components/NluIntentMatrix';
import { AntiGhostingLedger } from './components/AntiGhostingLedger';
import { AtomicReservationGrid } from './components/AtomicReservationGrid';
import { ResilientAgentDesk } from './components/ResilientAgentDesk';
import { PiiNdpaVault } from './components/PiiNdpaVault';
import { 
  INITIAL_CHAT_MESSAGES, 
  INITIAL_WEBHOOK_LOGS, 
  INITIAL_LEADS, 
  INITIAL_SLOTS, 
  INITIAL_CARTS, 
  INITIAL_LEDGER_ENTRIES, 
  INITIAL_AGENTS, 
  INITIAL_NDPA_RECORDS 
} from './data/mockData';
import { ChatMessage, WebhookLog, LeadScore, ReservationSlot, AntiGhostingCart, LedgerEntry, AgentProfile, NdpaConsentRecord } from './types';

export default function App() {
  const [activeTab, setActiveTab] = useState<string>('simulator');
  const [messages, setMessages] = useState<ChatMessage[]>(INITIAL_CHAT_MESSAGES);
  const [webhookLogs, setWebhookLogs] = useState<WebhookLog[]>(INITIAL_WEBHOOK_LOGS);
  const [leads, setLeads] = useState<LeadScore[]>(INITIAL_LEADS);
  const [slots, setSlots] = useState<ReservationSlot[]>(INITIAL_SLOTS);
  const [carts, setCarts] = useState<AntiGhostingCart[]>(INITIAL_CARTS);
  const [ledgerEntries, setLedgerEntries] = useState<LedgerEntry[]>(INITIAL_LEDGER_ENTRIES);
  const [agents, setAgents] = useState<AgentProfile[]>(INITIAL_AGENTS);
  const [ndpaRecords, setNdpaRecords] = useState<NdpaConsentRecord[]>(INITIAL_NDPA_RECORDS);

  const [isLoading, setIsLoading] = useState(false);
  const [stats, setStats] = useState({
    totalWebhooks: 142,
    tokensSaved: 84500,
    nairaSaved: 67600,
    activeHolds: 3,
  });

  // Handler: Send message in WhatsApp simulator
  const handleSendMessage = async (text: string) => {
    const userMsgId = `msg-${Date.now()}`;
    const userMsg: ChatMessage = {
      id: userMsgId,
      sender: 'user',
      text,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      status: 'delivered',
    };

    setMessages((prev) => [...prev, userMsg]);
    setIsLoading(true);

    // Record webhook ingress log (< 25ms decoupled simulation)
    const newWebhookLog: WebhookLog = {
      id: `wh-${Math.floor(Math.random() * 90000 + 10000)}`,
      timestamp: new Date().toLocaleTimeString(),
      event: 'messages.received',
      phone: '+2348031234567',
      rawPayload: {
        object: 'whatsapp_business_account',
        entry: [
          {
            id: 'WHATSAPP_BIZ_9021',
            changes: [
              {
                value: {
                  messages: [{ from: '2348031234567', text: { body: text }, type: 'text' }],
                },
              },
            ],
          },
        ],
      },
      signatureVerified: true,
      httpStatus: 200,
      ackLatencyMs: Math.floor(Math.random() * 12 + 10),
      workerStatus: 'completed',
      workerLatencyMs: Math.floor(Math.random() * 25 + 20),
    };
    setWebhookLogs((prev) => [newWebhookLog, ...prev]);

    try {
      // Call backend NLU and Gemini escalation
      const res = await fetch('/api/nlu/process', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text,
          customerPhone: '+2348031234567',
          customerName: 'Tunde Adeleke',
          previousContext: messages.map((m) => ({ sender: m.sender, text: m.text })),
        }),
      });

      const data = await res.json();

      const botMsgId = `msg-${Date.now() + 1}`;
      const botMsg: ChatMessage = {
        id: botMsgId,
        sender: 'bot',
        text: data.suggestedReply || 'Thank you for your message! Our Nigerian SME team is processing your request.',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        status: 'read',
        interactiveType: data.intent === 'INSTANT_CHECKOUT_ORDER' ? 'payment_link' : undefined,
        metadata: {
          intent: data.intent,
          leadTier: data.leadTier,
          isFastPath: data.source === 'FAST_PATH_DETERMINISTIC',
          latencyMs: data.latencyMs,
          amountNaira: data.intent === 'INSTANT_CHECKOUT_ORDER' ? 73500 : undefined,
          bankName: 'Moniepoint MFB',
          accountNumber: '9031842901',
          holdExpiry: new Date(Date.now() + 10 * 60 * 1000).toISOString(),
        },
      };

      setMessages((prev) => [...prev, botMsg]);

      // Update lead scoring list if new intent classified
      if (data.intent) {
        setLeads((prev) => [
          {
            phone: '+2348031234567',
            name: 'Tunde Adeleke (Ikeja)',
            urgencyScore: data.urgencyScore || 8,
            budgetNaira: data.intent === 'INSTANT_CHECKOUT_ORDER' ? 73500 : 45000,
            techComplexity: data.source === 'FAST_PATH_DETERMINISTIC' ? 2 : 6,
            tier: data.leadTier || 'HOT',
            detectedIntent: data.intent,
            suggestedAction: data.action || 'AUTO_RESERVE_HOLD',
            dialectDetected: data.dialect || 'Nigerian Pidgin',
            extractedEntities: data.entities || {},
          },
          ...prev.slice(0, 5),
        ]);
      }

      // Update stats
      if (data.source === 'FAST_PATH_DETERMINISTIC') {
        setStats((prev) => ({
          ...prev,
          totalWebhooks: prev.totalWebhooks + 1,
          tokensSaved: prev.tokensSaved + 650,
          nairaSaved: prev.nairaSaved + 520,
        }));
      } else {
        setStats((prev) => ({
          ...prev,
          totalWebhooks: prev.totalWebhooks + 1,
        }));
      }
    } catch (err) {
      console.error('NLU processing error:', err);
    } finally {
      setIsLoading(false);
    }
  };

  // Handler: Simulate Bank Transfer / NIBSS Settlement Webhook
  const handleSimulateBankTransfer = async (ref: string, amount: number) => {
    setIsLoading(true);

    // 1. Log incoming bank settlement webhook
    const bankWebhook: WebhookLog = {
      id: `wh-bank-${Date.now()}`,
      timestamp: new Date().toLocaleTimeString(),
      event: 'bank_transfer.settled',
      phone: '+2348031234567',
      rawPayload: {
        event: 'charge.success',
        data: {
          reference: ref,
          amount: amount * 100, // Kobo
          channel: 'dedicated_virtual_nuban',
          bank: 'Moniepoint MFB',
          paid_at: new Date().toISOString(),
        },
      },
      signatureVerified: true,
      httpStatus: 200,
      ackLatencyMs: 14,
      workerStatus: 'completed',
      workerLatencyMs: 38,
    };
    setWebhookLogs((prev) => [bankWebhook, ...prev]);

    // 2. Add Settled Ledger Entry ($Assets = Liabilities + Equity$)
    const newLedgerEntry: LedgerEntry = {
      id: `led-${Date.now()}`,
      timestamp: new Date().toLocaleTimeString(),
      ref,
      customer: 'Tunde Adeleke (+2348031234567)',
      debitAccount: 'Moniepoint Virtual Clearing (Assets)',
      creditAccount: 'Product Sales Revenue (Equity)',
      amountNaira: amount,
      assets: 268500,
      liabilities: 45000,
      equity: 223500,
      isBalanced: true,
      status: 'SETTLED',
    };
    setLedgerEntries((prev) => [newLedgerEntry, ...prev]);

    // 3. Proactively push WhatsApp receipt into chat
    const receiptMsg: ChatMessage = {
      id: `msg-${Date.now()}`,
      sender: 'bot',
      text: `🎉 *PAYMENT RECEIVED & CONFIRMED!*\n\n🧾 *Receipt Reference:* ${ref}\n💰 *Amount Cleared:* ₦${amount.toLocaleString()}\n🏦 *Settlement Rail:* Moniepoint MFB / NIBSS Instant Pay\n\nYour 3 cartons of Kings Pure Vegetable Oil don enter priority packing queue for Allen Avenue, Ikeja dispatch. Our rider go call you once he dey on the way! 🚚💨`,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      status: 'read',
      metadata: {
        intent: 'PAYMENT_SETTLED_RECEIPT',
        leadTier: 'HOT',
        isFastPath: true,
        latencyMs: 16,
      },
    };

    setMessages((prev) => [...prev, receiptMsg]);

    // Update active carts state
    setCarts((prev) =>
      prev.map((c) =>
        c.sessionId === 'SESS_LAG_8821' ? { ...c, status: 'PAYMENT_RECEIVED', receiptPushed: true } : c
      )
    );

    setIsLoading(false);
  };

  // Handler: Book atomic slot
  const handleBookSlot = async (slotId: string, phone: string) => {
    setSlots((prev) =>
      prev.map((s) =>
        s.id === slotId
          ? {
              ...s,
              status: 'HELD_PENDING_PAYMENT',
              heldByPhone: phone,
              holdExpiresAt: new Date(Date.now() + 10 * 60 * 1000).toISOString(),
              transactionRef: `HOLD_${slotId}_${Math.floor(Math.random() * 9000 + 1000)}`,
            }
          : s
      )
    );
  };

  const handleReleaseSlot = (slotId: string) => {
    setSlots((prev) =>
      prev.map((s) => (s.id === slotId ? { ...s, status: 'AVAILABLE', heldByPhone: undefined } : s))
    );
  };

  const handleConfirmSlotPayment = (slotId: string) => {
    setSlots((prev) =>
      prev.map((s) =>
        s.id === slotId ? { ...s, status: 'CONFIRMED', transactionRef: `SETTLED_${Date.now()}` } : s
      )
    );
  };

  // Handler: Toggle agent status (NEPA power outage simulation)
  const handleToggleAgentStatus = (agentId: string) => {
    setAgents((prev) =>
      prev.map((ag) =>
        ag.id === agentId
          ? {
              ...ag,
              status: ag.status === 'ONLINE' ? 'OFFLINE_NEPA' : 'ONLINE',
              lastHeartbeat: ag.status === 'ONLINE' ? '1m ago (Broadband Dropout)' : 'Just now',
            }
          : ag
      )
    );
  };

  // Handler: Reset Chat
  const handleResetChat = () => {
    setMessages(INITIAL_CHAT_MESSAGES);
  };

  // Backend API Call Helpers
  const handleTestNlu = async (text: string) => {
    const res = await fetch('/api/nlu/process', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text }),
    });
    return res.json();
  };

  const handleSanitizeTest = async (text: string) => {
    const res = await fetch('/api/pii/sanitize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    return res.json();
  };

  const handleValidateLedger = async (data: any) => {
    const res = await fetch('/api/ledger/validate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return res.json();
  };

  const handleGenerateContextInjection = async (customerName: string, customerPhone: string) => {
    const res = await fetch('/api/agent/generate-context', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        customerName,
        customerPhone,
        chatHistory: messages.map((m) => ({ sender: m.sender, text: m.text })),
      }),
    });
    return res.json();
  };

  const handleTriggerWebhook = async (event: string, payload: any) => {
    const res = await fetch('/api/webhook/whatsapp', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();

    const newLog: WebhookLog = {
      id: `wh-${Math.floor(Math.random() * 90000 + 10000)}`,
      timestamp: new Date().toLocaleTimeString(),
      event,
      phone: payload.entry?.[0]?.changes?.[0]?.value?.contacts?.[0]?.wa_id || '+2348000000000',
      rawPayload: payload,
      signatureVerified: true,
      httpStatus: 200,
      ackLatencyMs: data.ackLatencyMs || 18,
      workerStatus: 'completed',
      workerLatencyMs: 42,
    };
    setWebhookLogs((prev) => [newLog, ...prev]);
  };

  return (
    <div className="min-h-screen bg-[#0a0a0b] text-gray-200 font-sans flex flex-col selection:bg-emerald-500/20 selection:text-emerald-400">
      {/* Executive Header & Navigation */}
      <Header activeTab={activeTab} setActiveTab={setActiveTab} stats={stats} />

      {/* Main Workspace Container */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 py-6">
        {activeTab === 'simulator' && (
          <WhatsAppPhoneSimulator
            messages={messages}
            onSendMessage={handleSendMessage}
            isLoading={isLoading}
            onSimulateBankTransfer={handleSimulateBankTransfer}
            onResetChat={handleResetChat}
          />
        )}

        {activeTab === 'webhooks' && (
          <WebhookInspector logs={webhookLogs} onTriggerWebhook={handleTriggerWebhook} />
        )}

        {activeTab === 'nlu' && (
          <NluIntentMatrix leads={leads} onTestNlu={handleTestNlu} />
        )}

        {activeTab === 'anti-ghosting' && (
          <AntiGhostingLedger
            carts={carts}
            ledgerEntries={ledgerEntries}
            onTriggerBankSettlement={handleSimulateBankTransfer}
            onValidateLedger={handleValidateLedger}
          />
        )}

        {activeTab === 'reservations' && (
          <AtomicReservationGrid
            slots={slots}
            onBookSlot={handleBookSlot}
            onReleaseSlot={handleReleaseSlot}
            onConfirmSlotPayment={handleConfirmSlotPayment}
          />
        )}

        {activeTab === 'handoff' && (
          <ResilientAgentDesk
            agents={agents}
            onToggleAgentStatus={handleToggleAgentStatus}
            onGenerateContextInjection={handleGenerateContextInjection}
          />
        )}

        {activeTab === 'pii-ndpa' && (
          <PiiNdpaVault ndpaRecords={ndpaRecords} onSanitizeTest={handleSanitizeTest} />
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-white/5 bg-[#0e0e10] py-4 text-xs text-gray-500">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 flex flex-col sm:flex-row items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
            <span>KudiFlow Enterprise &bull; WhatsApp Conversational Workflow Platform for Nigerian SMEs</span>
          </div>
          <div className="flex items-center gap-3 text-[11px]">
            <span className="text-emerald-400 font-mono">Meta Decoupled 200 OK</span>
            <span className="text-gray-700">&bull;</span>
            <span className="text-blue-400 font-mono">NDPA 2023 Compliant</span>
            <span className="text-gray-700">&bull;</span>
            <span className="text-purple-400 font-mono">Gemini 3.7 Flash</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
