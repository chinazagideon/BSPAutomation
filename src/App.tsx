import React, { useState, useEffect } from 'react';
import { Header } from './components/Header';
import { WhatsAppPhoneSimulator } from './components/WhatsAppPhoneSimulator';
import { WebhookInspector } from './components/WebhookInspector';
import { NluIntentMatrix } from './components/NluIntentMatrix';
import { AntiGhostingLedger } from './components/AntiGhostingLedger';
import { AtomicReservationGrid } from './components/AtomicReservationGrid';
import { ResilientAgentDesk } from './components/ResilientAgentDesk';
import { PiiNdpaVault } from './components/PiiNdpaVault';
import { APP_CONFIG } from './config/env';
import {
  INITIAL_CHAT_MESSAGES,
  INITIAL_WEBHOOK_LOGS,
  INITIAL_LEADS,
  INITIAL_SLOTS,
  INITIAL_CARTS,
  INITIAL_LEDGER_ENTRIES,
  INITIAL_AGENTS,
  INITIAL_NDPA_RECORDS,
} from './data/mockData';
import {
  useResetSandboxMutation,
  useSandboxBurstMutation,
  useSandboxInboundMutation,
  useSandboxStateQuery,
  useSendTemplateMutation,
  useUpdateFaultProfileMutation,
  useUpdateNluControllerMutation,
} from './hooks/useSandboxApi';
import { useSandboxStream } from './hooks/useSandboxStream';
import { apiClient } from './lib/apiClient';
import {
  ChatMessage,
  WebhookLog,
  LeadScore,
  ReservationSlot,
  AntiGhostingCart,
  LedgerEntry,
  AgentProfile,
  NdpaConsentRecord,
  SandboxFaultProfile,
  SandboxMerchant,
  SandboxNegotiationFrame,
  SandboxNluController,
  SandboxWindowState,
} from './types';

function mapSandboxMsgToChatMessage(raw: any, latestTrace?: any): ChatMessage {
  return {
    id: raw.id || `msg-${Date.now()}-${Math.random()}`,
    sender: raw.sender || 'bot',
    text: raw.text || '',
    timestamp:
      raw.timestamp ||
      new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    status: raw.status || 'read',
    interactiveType: raw.interactive_type || undefined,
    headerText: raw.header_text || undefined,
    buttonTitle: raw.button_title || undefined,
    buttons: raw.buttons || [],
    listSections: raw.list_sections || [],
    carouselCards: raw.carousel_cards || [],
    metadata: {
      ...(raw.metadata || {}),
      intent: raw.metadata?.intent || latestTrace?.intent,
      leadTier: raw.metadata?.leadTier || latestTrace?.lead_tier,
      routingSource: raw.metadata?.routingSource || latestTrace?.routing_source,
      isFastPath:
        raw.metadata?.isFastPath ??
        (latestTrace?.routing_source === 'FAST_PATH' ||
          latestTrace?.routing_source === 'NEGOTIATION_FRAME'),
      latencyMs: raw.metadata?.latencyMs || latestTrace?.latency_ms,
      bankName: raw.metadata?.bankName || APP_CONFIG.DEFAULT_VIRTUAL_BANK,
      accountNumber:
        raw.metadata?.accountNumber || APP_CONFIG.DEFAULT_VIRTUAL_ACCOUNT,
    },
  };
}

export default function App() {
  const [activeTab, setActiveTab] = useState<string>('simulator');
  const [messages, setMessages] = useState<ChatMessage[]>(INITIAL_CHAT_MESSAGES);
  const [webhookLogs, setWebhookLogs] = useState<WebhookLog[]>(INITIAL_WEBHOOK_LOGS);
  const [leads, setLeads] = useState<LeadScore[]>(INITIAL_LEADS);
  const [slots, setSlots] = useState<ReservationSlot[]>(INITIAL_SLOTS);
  const [carts, setCarts] = useState<AntiGhostingCart[]>(INITIAL_CARTS);
  const [ledgerEntries, setLedgerEntries] =
    useState<LedgerEntry[]>(INITIAL_LEDGER_ENTRIES);
  const [agents, setAgents] = useState<AgentProfile[]>(INITIAL_AGENTS);
  const [ndpaRecords, setNdpaRecords] =
    useState<NdpaConsentRecord[]>(INITIAL_NDPA_RECORDS);

  const [isBackendConnected, setIsBackendConnected] = useState<boolean>(false);
  const [merchants, setMerchants] = useState<SandboxMerchant[]>([
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
  ]);
  const [activePhoneNumberId, setActivePhoneNumberId] = useState<string>(
    APP_CONFIG.DEFAULT_PHONE_NUMBER_ID
  );
  const [activeProvider, setActiveProvider] = useState<string>(
    APP_CONFIG.DEFAULT_PROVIDER
  );
  const [faultProfile, setFaultProfile] = useState<SandboxFaultProfile>({
    force_rate_limit_429: false,
    force_upstream_500: false,
    simulate_delivery_failure: false,
    enforce_24h_window: true,
    clock_offset_hours: 0,
    duplicate_webhook_replay: false,
    corrupt_hmac_signature: false,
    network_latency_ms: 0,
  });
  const [nluController, setNluController] = useState<SandboxNluController>({
    use_fast_path: true,
    fast_path_confidence_threshold: 0.9,
    use_custom_model: true,
    custom_model_confidence_threshold: 0.75,
    use_llm_escalation: true,
    active_bsp_provider: 'META_CLOUD',
  });
  const [windowState, setWindowState] = useState<SandboxWindowState>({
    is_open: true,
    elapsed_hours: 0,
    remaining_seconds: 86400,
    remaining_hours: 24.0,
    clock_offset_hours: 0,
    enforce_24h_window: true,
  });
  const [activeFrame, setActiveFrame] =
    useState<SandboxNegotiationFrame | null>(null);

  const [isLoading, setIsLoading] = useState(false);
  const [stats, setStats] = useState({
    totalWebhooks: 142,
    tokensSaved: 84500,
    nairaSaved: 67600,
    activeHolds: 3,
  });

  // TanStack Query hooks for Sandbox State & Mutations
  const sandboxStateQuery = useSandboxStateQuery(
    activePhoneNumberId,
    APP_CONFIG.DEFAULT_CUSTOMER_PHONE
  );
  const inboundMutation = useSandboxInboundMutation(
    activePhoneNumberId,
    APP_CONFIG.DEFAULT_CUSTOMER_PHONE
  );
  const burstMutation = useSandboxBurstMutation(
    activePhoneNumberId,
    APP_CONFIG.DEFAULT_CUSTOMER_PHONE
  );
  const updateFaultMutation = useUpdateFaultProfileMutation(
    activePhoneNumberId,
    APP_CONFIG.DEFAULT_CUSTOMER_PHONE
  );
  const updateNluMutation = useUpdateNluControllerMutation(
    activePhoneNumberId,
    APP_CONFIG.DEFAULT_CUSTOMER_PHONE
  );
  const sendTemplateMutation = useSendTemplateMutation(
    activePhoneNumberId,
    APP_CONFIG.DEFAULT_CUSTOMER_PHONE
  );
  const resetSandboxMutation = useResetSandboxMutation(
    activePhoneNumberId,
    APP_CONFIG.DEFAULT_CUSTOMER_PHONE
  );

  // Hydrate local state when TanStack Query state resolves
  useEffect(() => {
    const data = sandboxStateQuery.data;
    if (!data) return;

    setIsBackendConnected(true);
    if (data.merchants?.length) setMerchants(data.merchants);
    if (data.fault_profile) setFaultProfile(data.fault_profile);
    if (data.nlu_controller) setNluController(data.nlu_controller);
    if (data.window_state) setWindowState(data.window_state);
    setActiveFrame(data.active_frame || null);

    if (Array.isArray(data.messages) && data.messages.length > 0) {
      const latestTrace = data.nlu_traces?.[0];
      setMessages(
        data.messages.map((m: any) => mapSandboxMsgToChatMessage(m, latestTrace))
      );
    }
    if (Array.isArray(data.webhook_logs) && data.webhook_logs.length > 0) {
      setWebhookLogs((prev) => [...data.webhook_logs, ...prev.slice(0, 15)]);
    }
  }, [sandboxStateQuery.data]);

  // Dedicated SSE stream hook
  useSandboxStream({
    onConnected: () => setIsBackendConnected(true),
    onWhatsAppMessage: (rawMsg) => {
      const msgObj = mapSandboxMsgToChatMessage(rawMsg);
      setMessages((prev) => {
        if (prev.some((existing) => existing.id === msgObj.id)) return prev;
        return [...prev, msgObj];
      });
    },
    onWebhookLog: (logEntry) => {
      setWebhookLogs((prev) => {
        if (prev.some((w) => w.id === logEntry.id)) return prev;
        return [logEntry, ...prev.slice(0, 40)];
      });
    },
    onNluTrace: (tr) => {
      if (tr.active_frame !== undefined) {
        setActiveFrame(tr.active_frame);
      }
      setLeads((prev) => [
        {
          phone: tr.customer_phone || APP_CONFIG.DEFAULT_CUSTOMER_DISPLAY_PHONE,
          name: tr.customer_name || APP_CONFIG.DEFAULT_CUSTOMER_NAME,
          urgencyScore: tr.urgency_score || 8,
          budgetNaira: 78000,
          techComplexity: tr.routing_source === 'FAST_PATH' ? 2 : 6,
          tier: tr.lead_tier || 'HOT',
          detectedIntent: tr.intent || 'GENERAL_INQUIRY',
          suggestedAction: tr.action || 'AUTO_RESERVE_HOLD',
          dialectDetected: tr.detected_dialect || 'Nigerian Pidgin',
          extractedEntities: tr.extracted_entities || {},
        },
        ...prev.slice(0, 10),
      ]);
    },
    onFaultProfileUpdated: (profile) => setFaultProfile(profile),
    onNluControllerUpdated: (ctrl) => setNluController(ctrl),
  });

  // Handler: Send message or interactive action in WhatsApp simulator
  const handleSendMessage = async (
    text: string,
    options?: {
      messageType?: string;
      interactiveId?: string;
      mediaId?: string;
      reactionEmoji?: string;
      location?: Record<string, any>;
    }
  ) => {
    setIsLoading(true);

    try {
      const data = await inboundMutation.mutateAsync({
        provider: activeProvider,
        phone_number_id: activePhoneNumberId,
        customer_phone: APP_CONFIG.DEFAULT_CUSTOMER_PHONE,
        customer_name: APP_CONFIG.DEFAULT_CUSTOMER_NAME,
        message_type: options?.messageType || 'text',
        text,
        interactive_id: options?.interactiveId,
        media_id: options?.mediaId,
        reaction_emoji: options?.reactionEmoji,
        location: options?.location,
        execute_worker_inline: true,
      });

      setIsBackendConnected(true);
      if (data.window_state) setWindowState(data.window_state);
      setActiveFrame(data.active_frame || null);

      if (Array.isArray(data.messages) && data.messages.length > 0) {
        const latestTrace = data.latest_nlu_trace;
        setMessages((prev) => {
          const incomingMapped = data.messages.map((m: any) =>
            mapSandboxMsgToChatMessage(m, latestTrace)
          );
          const existingIds = new Set(prev.map((m) => m.id));
          const newOnes = incomingMapped.filter(
            (m: ChatMessage) => !existingIds.has(m.id)
          );
          return newOnes.length > 0 ? [...prev, ...newOnes] : prev;
        });
      }

      if (data.webhook_log) {
        setWebhookLogs((prev) => {
          if (prev.some((w) => w.id === data.webhook_log.id)) return prev;
          return [data.webhook_log, ...prev];
        });
      }

      const tr = data.latest_nlu_trace;
      if (tr) {
        setLeads((prev) => [
          {
            phone: tr.customer_phone || APP_CONFIG.DEFAULT_CUSTOMER_DISPLAY_PHONE,
            name: tr.customer_name || APP_CONFIG.DEFAULT_CUSTOMER_NAME,
            urgencyScore: tr.urgency_score || 8,
            budgetNaira: 78000,
            techComplexity: tr.routing_source === 'FAST_PATH' ? 2 : 6,
            tier: tr.lead_tier || 'HOT',
            detectedIntent: tr.intent,
            suggestedAction: tr.action || 'AUTO_RESERVE_HOLD',
            dialectDetected: tr.detected_dialect || 'Nigerian Pidgin',
            extractedEntities: tr.extracted_entities || {},
          },
          ...prev.slice(0, 8),
        ]);

        if (tr.action === 'GENERATE_VIRTUAL_NUBAN_HOLD') {
          const newCart: AntiGhostingCart = {
            sessionId: `SESS_${Math.floor(Math.random() * 9000 + 1000)}`,
            customerPhone: APP_CONFIG.DEFAULT_CUSTOMER_DISPLAY_PHONE,
            customerName: APP_CONFIG.DEFAULT_CUSTOMER_NAME,
            items: [
              {
                name:
                  tr.extracted_entities?.bound_slots?.product_name ||
                  'Catalog Item',
                quantity: Number(
                  tr.extracted_entities?.bound_slots?.quantity || 1
                ),
                unitPrice: 78000,
              },
            ],
            totalNaira: Number(
              (tr.extracted_entities?.calculated_total_kobo || 7800000) / 100
            ),
            virtualAccount: {
              bank: APP_CONFIG.DEFAULT_VIRTUAL_BANK,
              accountNumber: APP_CONFIG.DEFAULT_VIRTUAL_ACCOUNT,
              accountName: 'Alaba Agro Depot',
              ref: `MNP_HOLD_${Date.now()}`,
            },
            status: 'WAITING_FOR_TRANSFER',
            createdAt: 'Just now',
            holdExpiresAt: '10m remaining',
            receiptPushed: false,
          };
          setCarts((prev) => [newCart, ...prev]);
        }
      }

      if (data.worker_result?.status === 'OPTED_OUT') {
        setNdpaRecords((prev) => [
          {
            id: `NDPA-${Date.now()}`,
            phone: APP_CONFIG.DEFAULT_CUSTOMER_DISPLAY_PHONE,
            consentType: 'MARKETING_BROADCAST',
            optInTimestamp: new Date().toLocaleTimeString(),
            ipAddress: '102.89.43.12 (MTN NG)',
            immutableHash: `sha256:${Math.random().toString(16).slice(2, 18)}`,
            status: 'REVOKED',
          },
          ...prev,
        ]);
      }

      setStats((prev) => ({
        ...prev,
        totalWebhooks: prev.totalWebhooks + 1,
        tokensSaved: prev.tokensSaved + (tr?.tokens_consumed === 0 ? 650 : 0),
        nairaSaved: prev.nairaSaved + (tr?.tokens_consumed === 0 ? 520 : 0),
      }));
      setIsLoading(false);
      return;
    } catch {
      // Fallback to local Express endpoint if Python FastAPI isn't running
    }

    const userMsg: ChatMessage = {
      id: `msg-${Date.now()}`,
      sender: 'user',
      text,
      timestamp: new Date().toLocaleTimeString([], {
        hour: '2-digit',
        minute: '2-digit',
      }),
      status: 'delivered',
    };
    setMessages((prev) => [...prev, userMsg]);

    try {
      const data = await apiClient.processFallbackNlu({
        message: text,
        previousContext: messages.map((m) => ({
          sender: m.sender,
          text: m.text,
        })),
      });

      const botMsg: ChatMessage = {
        id: `msg-${Date.now() + 1}`,
        sender: 'bot',
        text:
          data.suggestedReply ||
          'Thank you for your message! Our Nigerian SME team is processing your request.',
        timestamp: new Date().toLocaleTimeString([], {
          hour: '2-digit',
          minute: '2-digit',
        }),
        status: 'read',
        interactiveType:
          data.intent === 'INSTANT_CHECKOUT_ORDER' ? 'payment_link' : undefined,
        metadata: {
          intent: data.intent,
          leadTier: data.leadTier,
          isFastPath: data.source === 'FAST_PATH_DETERMINISTIC',
          latencyMs: data.latencyMs,
          amountNaira:
            data.intent === 'INSTANT_CHECKOUT_ORDER' ? 73500 : undefined,
          bankName: APP_CONFIG.DEFAULT_VIRTUAL_BANK,
          accountNumber: APP_CONFIG.DEFAULT_VIRTUAL_ACCOUNT,
        },
      };
      setMessages((prev) => [...prev, botMsg]);
    } catch (err) {
      console.error('NLU processing error:', err);
    } finally {
      setIsLoading(false);
    }
  };

  // Handler: Fire 3-message rapid burst (tests 1.2s debounce)
  const handleSendBurst = async (burstMessages: string[]) => {
    setIsLoading(true);
    try {
      const data = await burstMutation.mutateAsync({
        provider: activeProvider,
        phone_number_id: activePhoneNumberId,
        messages: burstMessages,
      });
      if (Array.isArray(data?.messages)) {
        setMessages(data.messages.map((m: any) => mapSandboxMsgToChatMessage(m)));
      }
    } finally {
      setIsLoading(false);
    }
  };

  // Handler: Update Sandbox Fault Profile
  const handleUpdateFaultProfile = async (
    updates: Partial<SandboxFaultProfile>
  ) => {
    setFaultProfile((prev) => ({ ...prev, ...updates }));
    try {
      await updateFaultMutation.mutateAsync(updates);
    } catch {
      // local state updated
    }
  };

  // Handler: Update Runtime NLU Stage Controller
  const handleUpdateNluController = async (
    updates: Partial<SandboxNluController>
  ) => {
    setNluController((prev) => ({ ...prev, ...updates }));
    try {
      await updateNluMutation.mutateAsync(updates);
    } catch {
      // local state updated
    }
  };

  // Handler: Send Approved WhatsApp Business Template
  const handleSendTemplate = async (templateName: string) => {
    setIsLoading(true);
    try {
      const data = await sendTemplateMutation.mutateAsync({
        phone_number_id: activePhoneNumberId,
        template_name: templateName,
      });
      if (Array.isArray(data?.messages)) {
        setMessages(data.messages.map((m: any) => mapSandboxMsgToChatMessage(m)));
      }
    } finally {
      setIsLoading(false);
    }
  };

  // Handler: Simulate Bank Transfer / NIBSS Settlement Webhook
  const handleSimulateBankTransfer = async (ref: string, amount: number) => {
    setIsLoading(true);

    const bankWebhook: WebhookLog = {
      id: `wh-bank-${Date.now()}`,
      timestamp: new Date().toLocaleTimeString(),
      event: 'bank_transfer.settled',
      phone: APP_CONFIG.DEFAULT_CUSTOMER_DISPLAY_PHONE,
      rawPayload: {
        event: 'charge.success',
        data: {
          reference: ref,
          amount: amount * 100,
          channel: 'dedicated_virtual_nuban',
          bank: APP_CONFIG.DEFAULT_VIRTUAL_BANK,
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

    const newLedgerEntry: LedgerEntry = {
      id: `led-${Date.now()}`,
      timestamp: new Date().toLocaleTimeString(),
      ref,
      customer: `${APP_CONFIG.DEFAULT_CUSTOMER_NAME} (${APP_CONFIG.DEFAULT_CUSTOMER_DISPLAY_PHONE})`,
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

    const receiptMsg: ChatMessage = {
      id: `msg-${Date.now()}`,
      sender: 'bot',
      text: `🎉 *PAYMENT RECEIVED & CONFIRMED!*\n\n🧾 *Receipt Reference:* ${ref}\n💰 *Amount Cleared:* ₦${amount.toLocaleString()}\n🏦 *Settlement Rail:* ${APP_CONFIG.DEFAULT_VIRTUAL_BANK} / NIBSS Instant Pay\n\nYour order don enter priority packing queue for dispatch. Our rider go call you once he dey on the way! 🚚💨`,
      timestamp: new Date().toLocaleTimeString([], {
        hour: '2-digit',
        minute: '2-digit',
      }),
      status: 'read',
      metadata: {
        intent: 'PAYMENT_SETTLED_RECEIPT',
        leadTier: 'HOT',
        isFastPath: true,
        latencyMs: 16,
      },
    };

    setMessages((prev) => [...prev, receiptMsg]);
    setCarts((prev) =>
      prev.map((c, idx) =>
        idx === 0 ? { ...c, status: 'PAYMENT_RECEIVED', receiptPushed: true } : c
      )
    );
    setIsLoading(false);
  };

  const handleBookSlot = async (slotId: string, phone: string) => {
    setSlots((prev) =>
      prev.map((s) =>
        s.id === slotId
          ? {
              ...s,
              status: 'HELD_PENDING_PAYMENT',
              heldByPhone: phone,
              holdExpiresAt: new Date(
                Date.now() + 10 * 60 * 1000
              ).toISOString(),
              transactionRef: `HOLD_${slotId}_${Math.floor(
                Math.random() * 9000 + 1000
              )}`,
            }
          : s
      )
    );
  };

  const handleReleaseSlot = (slotId: string) => {
    setSlots((prev) =>
      prev.map((s) =>
        s.id === slotId
          ? { ...s, status: 'AVAILABLE', heldByPhone: undefined }
          : s
      )
    );
  };

  const handleConfirmSlotPayment = (slotId: string) => {
    setSlots((prev) =>
      prev.map((s) =>
        s.id === slotId
          ? { ...s, status: 'CONFIRMED', transactionRef: `SETTLED_${Date.now()}` }
          : s
      )
    );
  };

  const handleToggleAgentStatus = (agentId: string) => {
    setAgents((prev) =>
      prev.map((ag) =>
        ag.id === agentId
          ? {
              ...ag,
              status: ag.status === 'ONLINE' ? 'OFFLINE_NEPA' : 'ONLINE',
              lastHeartbeat:
                ag.status === 'ONLINE'
                  ? '1m ago (Broadband Dropout)'
                  : 'Just now',
            }
          : ag
      )
    );
  };

  const handleResetChat = async () => {
    try {
      await resetSandboxMutation.mutateAsync();
    } catch {
      // ignore if offline
    }
    setMessages(INITIAL_CHAT_MESSAGES);
    setActiveFrame(null);
  };

  const handleTestNlu = (text: string) =>
    apiClient.processFallbackNlu({ message: text });

  const handleSanitizeTest = (text: string) => apiClient.sanitizePii(text);

  const handleValidateLedger = (data: any) => apiClient.validateLedger(data);

  const handleGenerateContextInjection = (
    customerName: string,
    customerPhone: string
  ) =>
    apiClient.generateAgentContext({
      customerName,
      customerPhone,
      chatHistory: messages.map((m) => ({ sender: m.sender, text: m.text })),
    });

  const handleTriggerWebhook = async (event: string, payload: any) => {
    try {
      const data = await apiClient.triggerProviderWebhook(
        activeProvider,
        payload
      );
      const newLog: WebhookLog = {
        id: data.event_id || `wh-${Math.floor(Math.random() * 90000 + 10000)}`,
        timestamp: new Date().toLocaleTimeString(),
        event: `${event} (${activeProvider})`,
        phone:
          payload.entry?.[0]?.changes?.[0]?.value?.contacts?.[0]?.wa_id ||
          APP_CONFIG.DEFAULT_CUSTOMER_DISPLAY_PHONE,
        rawPayload: payload,
        signatureVerified: data.signature_verified ?? true,
        httpStatus: 200,
        ackLatencyMs: data.ack_latency_ms || 12,
        workerStatus: 'completed',
        workerLatencyMs: 28,
      };
      setWebhookLogs((prev) => [newLog, ...prev]);
      return;
    } catch {
      // Fallback to Express
    }

    const data = await apiClient.triggerFallbackWebhook(payload);
    const newLog: WebhookLog = {
      id: `wh-${Math.floor(Math.random() * 90000 + 10000)}`,
      timestamp: new Date().toLocaleTimeString(),
      event,
      phone:
        payload.entry?.[0]?.changes?.[0]?.value?.contacts?.[0]?.wa_id ||
        APP_CONFIG.DEFAULT_CUSTOMER_DISPLAY_PHONE,
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
      <Header activeTab={activeTab} setActiveTab={setActiveTab} stats={stats} />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 py-6">
        {activeTab === 'simulator' && (
          <WhatsAppPhoneSimulator
            messages={messages}
            onSendMessage={handleSendMessage}
            isLoading={isLoading}
            onSimulateBankTransfer={handleSimulateBankTransfer}
            onResetChat={handleResetChat}
            merchants={merchants}
            activePhoneNumberId={activePhoneNumberId}
            onSelectMerchantPhoneId={setActivePhoneNumberId}
            activeProvider={activeProvider}
            onSelectProvider={setActiveProvider}
            faultProfile={faultProfile}
            onUpdateFaultProfile={handleUpdateFaultProfile}
            nluController={nluController}
            onUpdateNluController={handleUpdateNluController}
            windowState={windowState}
            activeFrame={activeFrame}
            onSendBurst={handleSendBurst}
            onSendTemplate={handleSendTemplate}
            isBackendConnected={isBackendConnected}
          />
        )}

        {activeTab === 'webhooks' && (
          <WebhookInspector
            logs={webhookLogs}
            onTriggerWebhook={handleTriggerWebhook}
          />
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
          <PiiNdpaVault
            ndpaRecords={ndpaRecords}
            onSanitizeTest={handleSanitizeTest}
          />
        )}
      </main>

      <footer className="border-t border-white/5 bg-[#0e0e10] py-4 text-xs text-gray-500">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 flex flex-col sm:flex-row items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
            <span>
              KudiFlow Enterprise &bull; WhatsApp Conversational Workflow Platform
              for Nigerian SMEs
            </span>
          </div>
          <div className="flex items-center gap-3 text-[11px]">
            <span className="text-emerald-400 font-mono">
              Multi-Provider /webhooks/&#123;provider&#125;
            </span>
            <span className="text-gray-700">&bull;</span>
            <span className="text-blue-400 font-mono">NDPA 2023 Compliant</span>
            <span className="text-gray-700">&bull;</span>
            <span className="text-purple-400 font-mono">Local BSP Sandbox</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
