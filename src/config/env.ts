/// <reference types="vite/client" />

/**
 * Centralized Frontend Environment & Sandbox Configuration.
 * Reads from Vite `import.meta.env.VITE_*` variables with safe defaults for local development.
 */
export const APP_CONFIG = {
  API_V1_BASE: import.meta.env.VITE_API_V1_BASE || '/api/v1',
  LEGACY_API_BASE: import.meta.env.VITE_LEGACY_API_BASE || '/api',
  SANDBOX_STREAM_URL: import.meta.env.VITE_SANDBOX_STREAM_URL || '/api/v1/sandbox/stream',
  DEFAULT_CUSTOMER_PHONE: import.meta.env.VITE_SANDBOX_CUSTOMER_PHONE || '2348031234567',
  DEFAULT_CUSTOMER_DISPLAY_PHONE:
    import.meta.env.VITE_SANDBOX_CUSTOMER_DISPLAY_PHONE || '+2348031234567',
  DEFAULT_CUSTOMER_NAME: import.meta.env.VITE_SANDBOX_CUSTOMER_NAME || 'Tunde Adeleke',
  DEFAULT_PHONE_NUMBER_ID:
    import.meta.env.VITE_SANDBOX_PHONE_NUMBER_ID || 'meta_phone_alaba_agro',
  DEFAULT_PROVIDER: import.meta.env.VITE_SANDBOX_PROVIDER || 'whatsapp',
  DEFAULT_VIRTUAL_BANK: import.meta.env.VITE_DEFAULT_VIRTUAL_BANK || 'Moniepoint MFB',
  DEFAULT_VIRTUAL_ACCOUNT: import.meta.env.VITE_DEFAULT_VIRTUAL_ACCOUNT || '9031842901',
} as const;
