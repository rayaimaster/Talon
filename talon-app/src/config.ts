const API_URL_KEY = 'talon_admin_api_url';
const ADMIN_TOKEN_KEY = 'talon_admin_api_token';

export interface StoredConfig {
  apiBaseUrl: string;
  adminToken: string;
}

function normalizeApiBaseUrl(value: string): string {
  return value.trim().replace(/\/+$/, '');
}

export function getStoredConfig(): StoredConfig {
  const envUrl = import.meta.env.VITE_API_URL?.trim() ?? '';
  const envToken = import.meta.env.VITE_ADMIN_API_TOKEN?.trim() ?? '';

  const apiBaseUrl = normalizeApiBaseUrl(
    window.localStorage.getItem(API_URL_KEY) ?? envUrl ?? '',
  );
  const adminToken = window.localStorage.getItem(ADMIN_TOKEN_KEY) ?? envToken ?? '';

  return { apiBaseUrl, adminToken };
}

export function saveStoredConfig(config: StoredConfig): StoredConfig {
  const normalized = {
    apiBaseUrl: normalizeApiBaseUrl(config.apiBaseUrl),
    adminToken: config.adminToken.trim(),
  };

  window.localStorage.setItem(API_URL_KEY, normalized.apiBaseUrl);
  window.localStorage.setItem(ADMIN_TOKEN_KEY, normalized.adminToken);
  return normalized;
}

export function clearStoredConfig(): void {
  window.localStorage.removeItem(API_URL_KEY);
  window.localStorage.removeItem(ADMIN_TOKEN_KEY);
}
