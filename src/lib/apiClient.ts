import { APP_CONFIG } from '../config/env';
import {
  SandboxFaultProfile,
  SandboxMerchant,
  SandboxNegotiationFrame,
  SandboxNluController,
  SandboxWindowState,
} from '../types';

export interface SandboxStateResponse {
  merchants: SandboxMerchant[];
  active_merchant_id: string;
  phone_number_id: string;
  customer_phone: string;
  fault_profile: SandboxFaultProfile;
  nlu_controller: SandboxNluController;
  window_state: SandboxWindowState;
  active_frame: SandboxNegotiationFrame | null;
  context_stack?: SandboxNegotiationFrame[];
  messages: any[];
  webhook_logs: any[];
  nlu_traces: any[];
  templates: any[];
}

export interface InboundTurnPayload {
  provider: string;
  phone_number_id: string;
  customer_phone?: string;
  customer_name?: string;
  message_type?: string;
  text: string;
  interactive_id?: string;
  media_id?: string;
  reaction_emoji?: string;
  location?: Record<string, any>;
  execute_worker_inline?: boolean;
}

export interface BurstTurnPayload {
  provider: string;
  phone_number_id: string;
  customer_phone?: string;
  customer_name?: string;
  messages: string[];
  inter_message_delay_ms?: number;
}

export interface SendTemplatePayload {
  phone_number_id: string;
  to_phone?: string;
  template_name: string;
  language_code?: string;
  parameters?: string[];
}

class HttpClientError extends Error {
  status: number;
  data: any;

  constructor(message: string, status: number, data?: any) {
    super(message);
    this.name = 'HttpClientError';
    this.status = status;
    this.data = data;
  }
}

async function request<T>(url: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...((options.headers as Record<string, string>) || {}),
  };

  const response = await fetch(url, {
    ...options,
    headers,
  });

  const text = await response.text();
  let parsed: any = null;
  if (text) {
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = text;
    }
  }

  if (!response.ok) {
    throw new HttpClientError(
      parsed?.detail || parsed?.error || `HTTP ${response.status}`,
      response.status,
      parsed
    );
  }

  return parsed as T;
}

export const apiClient = {
  // Sandbox Control Plane Endpoints (/api/v1/sandbox/*)
  getSandboxState: (
    phoneNumberId: string = APP_CONFIG.DEFAULT_PHONE_NUMBER_ID,
    customerPhone: string = APP_CONFIG.DEFAULT_CUSTOMER_PHONE
  ) =>
    request<SandboxStateResponse>(
      `${APP_CONFIG.API_V1_BASE}/sandbox/state?phone_number_id=${encodeURIComponent(
        phoneNumberId
      )}&customer_phone=${encodeURIComponent(customerPhone)}`
    ),

  sendSandboxInbound: (payload: InboundTurnPayload) =>
    request<any>(`${APP_CONFIG.API_V1_BASE}/sandbox/inbound`, {
      method: 'POST',
      body: JSON.stringify({
        customer_phone: APP_CONFIG.DEFAULT_CUSTOMER_PHONE,
        customer_name: APP_CONFIG.DEFAULT_CUSTOMER_NAME,
        message_type: 'text',
        execute_worker_inline: true,
        ...payload,
      }),
    }),

  sendSandboxBurst: (payload: BurstTurnPayload) =>
    request<any>(`${APP_CONFIG.API_V1_BASE}/sandbox/burst`, {
      method: 'POST',
      body: JSON.stringify({
        customer_phone: APP_CONFIG.DEFAULT_CUSTOMER_PHONE,
        customer_name: APP_CONFIG.DEFAULT_CUSTOMER_NAME,
        inter_message_delay_ms: 120,
        ...payload,
      }),
    }),

  updateFaultProfile: (updates: Partial<SandboxFaultProfile>) =>
    request<{ status: string; fault_profile: SandboxFaultProfile }>(
      `${APP_CONFIG.API_V1_BASE}/sandbox/faults`,
      {
        method: 'PATCH',
        body: JSON.stringify(updates),
      }
    ),

  updateNluController: (updates: Partial<SandboxNluController>) =>
    request<{ status: string; nlu_controller: SandboxNluController }>(
      `${APP_CONFIG.API_V1_BASE}/sandbox/nlu-controller`,
      {
        method: 'PATCH',
        body: JSON.stringify(updates),
      }
    ),

  sendTemplateMessage: (payload: SendTemplatePayload) =>
    request<any>(`${APP_CONFIG.API_V1_BASE}/sandbox/send-template`, {
      method: 'POST',
      body: JSON.stringify({
        to_phone: APP_CONFIG.DEFAULT_CUSTOMER_PHONE,
        language_code: 'en',
        parameters: [APP_CONFIG.DEFAULT_CUSTOMER_NAME, 'Alaba Agro Depot'],
        ...payload,
      }),
    }),

  resetSandboxSession: (
    phoneNumberId: string = APP_CONFIG.DEFAULT_PHONE_NUMBER_ID,
    customerPhone: string = APP_CONFIG.DEFAULT_CUSTOMER_PHONE
  ) =>
    request<{ status: string; merchant_id: string }>(
      `${APP_CONFIG.API_V1_BASE}/sandbox/reset?phone_number_id=${encodeURIComponent(
        phoneNumberId
      )}&customer_phone=${encodeURIComponent(customerPhone)}`,
      { method: 'POST' }
    ),

  clearSandboxTelemetry: () =>
    request<{ status: string }>(`${APP_CONFIG.API_V1_BASE}/sandbox/telemetry`, {
      method: 'DELETE',
    }),

  triggerProviderWebhook: (provider: string, payload: Record<string, any>) =>
    request<any>(`${APP_CONFIG.API_V1_BASE}/ingress/webhooks/${encodeURIComponent(provider)}`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  // Express Fallback / Auxiliary Workbench Endpoints (/api/*)
  processFallbackNlu: (payload: {
    message: string;
    customerPhone?: string;
    customerName?: string;
    previousContext?: Array<{ sender: string; text: string }>;
  }) =>
    request<any>(`${APP_CONFIG.LEGACY_API_BASE}/nlu/process`, {
      method: 'POST',
      body: JSON.stringify({
        customerPhone: APP_CONFIG.DEFAULT_CUSTOMER_DISPLAY_PHONE,
        customerName: APP_CONFIG.DEFAULT_CUSTOMER_NAME,
        ...payload,
      }),
    }),

  sanitizePii: (text: string) =>
    request<any>(`${APP_CONFIG.LEGACY_API_BASE}/pii/sanitize`, {
      method: 'POST',
      body: JSON.stringify({ text }),
    }),

  validateLedger: (data: Record<string, any>) =>
    request<any>(`${APP_CONFIG.LEGACY_API_BASE}/ledger/validate`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  generateAgentContext: (payload: {
    customerName: string;
    customerPhone: string;
    chatHistory: Array<{ sender: string; text: string }>;
  }) =>
    request<any>(`${APP_CONFIG.LEGACY_API_BASE}/agent/generate-context`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  triggerFallbackWebhook: (payload: Record<string, any>) =>
    request<any>(`${APP_CONFIG.LEGACY_API_BASE}/webhook/whatsapp`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
};
