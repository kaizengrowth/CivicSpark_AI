/**
 * API Configuration
 * Handles different environments and API endpoints
 */

// Get the base URL for API calls
const getApiBaseUrl = (): string => {
  // In development and production, use relative URLs
  // Vite proxy handles development, CloudFront handles production
  return '';
};

export const API_BASE_URL = getApiBaseUrl();

export const API_ENDPOINTS = {
  // Meetings
  meetings: '/api/v1/meetings/',
  meetingById: (id: number) => `/api/v1/meetings/${id}`,
  meetingItems: (id: number) => `/api/v1/meetings/${id}/items`,
  agendaItemById: (id: number) => `/api/v1/meetings/items/${id}`,

  // Evidence layer
  search: '/api/v1/search/',
  ingestStatus: '/api/v1/ingest/status',

  // Auth
  login: '/api/v1/auth/login',
  register: '/api/v1/auth/register',
  profile: '/api/v1/auth/me',

  // Chatbot
  chatbot: '/api/v1/chatbot/chat',

  // Subscriptions
  subscriptions: '/api/v1/subscriptions/',
  subscriptionById: (id: number) => `/api/v1/subscriptions/${id}`,
  subscriptionTopics: '/api/v1/subscriptions/topics',
  testSms: '/api/v1/subscriptions/test-sms',

  // Representatives
  composeEmail: '/api/v1/representatives/compose-email',
  findRepresentatives: '/api/v1/representatives/find',

  // Organizations
  organizations: '/api/v1/organizations/',
  organizationById: (id: number) => `/api/v1/organizations/${id}`,
  organizationBySlug: (slug: string) => `/api/v1/organizations/slug/${slug}`,
};

/**
 * Make an API request with proper error handling
 */
export const apiRequest = async <T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> => {
  const url = `${API_BASE_URL}${endpoint}`;

  const defaultOptions: RequestInit = {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  };

  const response = await fetch(url, defaultOptions);

  if (!response.ok) {
    let errorMessage = `HTTP error! status: ${response.status}`;
    try {
      const errorText = await response.text();
      errorMessage += `, text: ${errorText}`;
    } catch {
      // response body was unreadable; keep the status-only message
    }
    throw new Error(errorMessage);
  }

  return response.json();
};

export default {
  API_BASE_URL,
  API_ENDPOINTS,
  apiRequest,
};
