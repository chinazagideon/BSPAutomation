import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { APP_CONFIG } from '../config/env';
import {
  apiClient,
  BurstTurnPayload,
  InboundTurnPayload,
  SendTemplatePayload,
} from '../lib/apiClient';
import { SandboxFaultProfile, SandboxNluController } from '../types';

export const SANDBOX_QUERY_KEYS = {
  state: (phoneNumberId: string, customerPhone: string) =>
    ['sandbox-state', phoneNumberId, customerPhone] as const,
};

export function useSandboxStateQuery(
  phoneNumberId: string = APP_CONFIG.DEFAULT_PHONE_NUMBER_ID,
  customerPhone: string = APP_CONFIG.DEFAULT_CUSTOMER_PHONE
) {
  return useQuery({
    queryKey: SANDBOX_QUERY_KEYS.state(phoneNumberId, customerPhone),
    queryFn: () => apiClient.getSandboxState(phoneNumberId, customerPhone),
    retry: false,
  });
}

export function useSandboxInboundMutation(
  phoneNumberId: string = APP_CONFIG.DEFAULT_PHONE_NUMBER_ID,
  customerPhone: string = APP_CONFIG.DEFAULT_CUSTOMER_PHONE
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: InboundTurnPayload) => apiClient.sendSandboxInbound(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: SANDBOX_QUERY_KEYS.state(phoneNumberId, customerPhone),
      });
    },
  });
}

export function useSandboxBurstMutation(
  phoneNumberId: string = APP_CONFIG.DEFAULT_PHONE_NUMBER_ID,
  customerPhone: string = APP_CONFIG.DEFAULT_CUSTOMER_PHONE
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: BurstTurnPayload) => apiClient.sendSandboxBurst(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: SANDBOX_QUERY_KEYS.state(phoneNumberId, customerPhone),
      });
    },
  });
}

export function useUpdateFaultProfileMutation(
  phoneNumberId: string = APP_CONFIG.DEFAULT_PHONE_NUMBER_ID,
  customerPhone: string = APP_CONFIG.DEFAULT_CUSTOMER_PHONE
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (updates: Partial<SandboxFaultProfile>) =>
      apiClient.updateFaultProfile(updates),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: SANDBOX_QUERY_KEYS.state(phoneNumberId, customerPhone),
      });
    },
  });
}

export function useUpdateNluControllerMutation(
  phoneNumberId: string = APP_CONFIG.DEFAULT_PHONE_NUMBER_ID,
  customerPhone: string = APP_CONFIG.DEFAULT_CUSTOMER_PHONE
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (updates: Partial<SandboxNluController>) =>
      apiClient.updateNluController(updates),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: SANDBOX_QUERY_KEYS.state(phoneNumberId, customerPhone),
      });
    },
  });
}

export function useSendTemplateMutation(
  phoneNumberId: string = APP_CONFIG.DEFAULT_PHONE_NUMBER_ID,
  customerPhone: string = APP_CONFIG.DEFAULT_CUSTOMER_PHONE
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: SendTemplatePayload) => apiClient.sendTemplateMessage(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: SANDBOX_QUERY_KEYS.state(phoneNumberId, customerPhone),
      });
    },
  });
}

export function useResetSandboxMutation(
  phoneNumberId: string = APP_CONFIG.DEFAULT_PHONE_NUMBER_ID,
  customerPhone: string = APP_CONFIG.DEFAULT_CUSTOMER_PHONE
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiClient.resetSandboxSession(phoneNumberId, customerPhone),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: SANDBOX_QUERY_KEYS.state(phoneNumberId, customerPhone),
      });
    },
  });
}

export function useClearSandboxTelemetryMutation(
  phoneNumberId: string = APP_CONFIG.DEFAULT_PHONE_NUMBER_ID,
  customerPhone: string = APP_CONFIG.DEFAULT_CUSTOMER_PHONE
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiClient.clearSandboxTelemetry(),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: SANDBOX_QUERY_KEYS.state(phoneNumberId, customerPhone),
      });
    },
  });
}
