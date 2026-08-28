export type MessageSender = 'user' | 'bot' | 'agent' | 'system';

export interface InteractiveButton {
  id: string;
  title: string;
  payload: string;
}

export interface InteractiveListRow {
  id: string;
  title: string;
  description?: string;
}

export interface InteractiveListSection {
  title: string;
  rows: InteractiveListRow[];
}

export interface ChatMessage {
  id: string;
  sender: MessageSender;
  text: string;
  timestamp: string;
  status?: 'sent' | 'delivered' | 'read';
  interactiveType?: 'buttons' | 'list' | 'payment_link' | 'receipt_card' | 'hold_timer';
  buttons?: InteractiveButton[];
  listSections?: InteractiveListSection[];
  metadata?: {
    intent?: string;
    leadTier?: 'HOT' | 'WARM' | 'COLD';
    sanitized?: boolean;
    piiEntitiesFound?: string[];
    holdExpiry?: string;
    amountNaira?: number;
    accountNumber?: string;
    bankName?: string;
    isFastPath?: boolean;
    latencyMs?: number;
  };
}

export interface WebhookLog {
  id: string;
  timestamp: string;
  event: string;
  phone: string;
  rawPayload: Record<string, any>;
  signatureVerified: boolean;
  httpStatus: number;
  ackLatencyMs: number;
  workerStatus: 'queued' | 'processing' | 'completed' | 'retrying';
  workerLatencyMs: number;
}

export interface LeadScore {
  phone: string;
  name: string;
  urgencyScore: number; // 1-10
  budgetNaira: number;
  techComplexity: number; // 1-10
  tier: 'HOT' | 'WARM' | 'COLD';
  detectedIntent: string;
  suggestedAction: string;
  dialectDetected: 'Nigerian Pidgin' | 'Commercial Slang' | 'Standard English' | 'Mixed';
  extractedEntities: {
    location?: string;
    quantity?: string;
    item?: string;
    timeline?: string;
  };
}

export interface ReservationSlot {
  id: string;
  service: string;
  agentName: string;
  startTime: string;
  endTime: string;
  priceNaira: number;
  status: 'AVAILABLE' | 'HELD_PENDING_PAYMENT' | 'CONFIRMED' | 'RELEASED';
  holdExpiresAt?: string;
  heldByPhone?: string;
  transactionRef?: string;
}

export interface AntiGhostingCart {
  sessionId: string;
  customerPhone: string;
  customerName: string;
  items: Array<{ name: string; quantity: number; unitPrice: number }>;
  totalNaira: number;
  virtualAccount: {
    bank: string;
    accountNumber: string;
    accountName: string;
    ref: string;
  };
  status: 'ACTIVE_CHATTING' | 'WAITING_FOR_TRANSFER' | 'PAYMENT_RECEIVED' | 'EXPIRED_RELEASED';
  createdAt: string;
  holdExpiresAt: string;
  receiptPushed: boolean;
}

export interface LedgerEntry {
  id: string;
  timestamp: string;
  ref: string;
  customer: string;
  debitAccount: string;
  creditAccount: string;
  amountNaira: number;
  assets: number;
  liabilities: number;
  equity: number;
  isBalanced: boolean;
  status: 'SETTLED' | 'MISMATCH_FLAGGED';
  aiExplanation?: string;
}

export interface AgentProfile {
  id: string;
  name: string;
  hub: 'Ikeja Tech Hub' | 'Lekki Phase 1' | 'Abuja Garki' | 'Yaba Central';
  status: 'ONLINE' | 'OFFLINE_NEPA' | 'BUSY' | 'ON_BREAK';
  activeChatsCount: number;
  latencyMs: number;
  lastHeartbeat: string;
}

export interface PiiRedactionResult {
  originalText: string;
  sanitizedText: string;
  redactedEntities: Array<{
    type: 'BVN' | 'NIN' | 'NUBAN' | 'CARD_PAN' | 'PHONE' | 'PASSWORD';
    value: string;
    token: string;
  }>;
  safetyScore: number;
}

export interface NdpaConsentRecord {
  id: string;
  phone: string;
  consentType: 'MARKETING_BROADCAST' | 'TRANSACTIONAL_UPDATES' | 'DATA_PROCESSING';
  optInTimestamp: string;
  ipAddress: string;
  immutableHash: string;
  status: 'ACTIVE' | 'REVOKED';
}
