import { useEffect, useRef } from 'react';
import { APP_CONFIG } from '../config/env';

export interface SandboxStreamCallbacks {
  onConnected?: () => void;
  onWhatsAppMessage?: (rawMsg: any) => void;
  onWebhookLog?: (logEntry: any) => void;
  onNluTrace?: (traceEntry: any) => void;
  onFaultProfileUpdated?: (profile: any) => void;
  onNluControllerUpdated?: (controller: any) => void;
}

/**
 * Custom hook encapsulating the Server-Sent Events (SSE) subscription to `/api/v1/sandbox/stream`.
 */
export function useSandboxStream(callbacks: SandboxStreamCallbacks) {
  const callbacksRef = useRef<SandboxStreamCallbacks>(callbacks);
  callbacksRef.current = callbacks;

  useEffect(() => {
    let es: EventSource | null = null;
    try {
      es = new EventSource(APP_CONFIG.SANDBOX_STREAM_URL);
      es.onmessage = (evt) => {
        try {
          const parsed = JSON.parse(evt.data);
          const cb = callbacksRef.current;

          if (parsed.type === 'connected' && parsed.mode !== 'fallback') {
            cb.onConnected?.();
          } else if (parsed.type === 'whatsapp_message' && parsed.data) {
            cb.onWhatsAppMessage?.(parsed.data);
          } else if (parsed.type === 'webhook_log' && parsed.data) {
            cb.onWebhookLog?.(parsed.data);
          } else if (parsed.type === 'nlu_trace' && parsed.data) {
            cb.onNluTrace?.(parsed.data);
          } else if (parsed.type === 'fault_profile_updated' && parsed.data) {
            cb.onFaultProfileUpdated?.(parsed.data);
          } else if (parsed.type === 'nlu_controller_updated' && parsed.data) {
            cb.onNluControllerUpdated?.(parsed.data);
          }
        } catch {
          // ignore malformed SSE frame
        }
      };
    } catch {
      // EventSource unsupported or offline
    }

    return () => {
      es?.close();
    };
  }, []);
}
