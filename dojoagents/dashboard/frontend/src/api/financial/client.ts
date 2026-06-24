export interface ApiResponse<T> {
  data: T;
  as_of?: string;
  source?: string;
  stale?: boolean;
}

export class FinancialApiClient {
  private baseUrl = '/api/v1';

  private async fetchWithHandling<T>(endpoint: string, options: RequestInit = {}): Promise<ApiResponse<T>> {
    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
    }

    const data = await response.json();
    return data;
  }

  async get<T>(endpoint: string, options?: RequestInit): Promise<ApiResponse<T>> {
    return this.fetchWithHandling<T>(endpoint, { ...options, method: 'GET' });
  }

  async post<T>(endpoint: string, body: any, options?: RequestInit): Promise<ApiResponse<T>> {
    return this.fetchWithHandling<T>(endpoint, {
      ...options,
      method: 'POST',
      body: JSON.stringify(body),
    });
  }

  async put<T>(endpoint: string, body: any, options?: RequestInit): Promise<ApiResponse<T>> {
    return this.fetchWithHandling<T>(endpoint, {
      ...options,
      method: 'PUT',
      body: JSON.stringify(body),
    });
  }

  async delete<T>(endpoint: string, options?: RequestInit): Promise<ApiResponse<T>> {
    return this.fetchWithHandling<T>(endpoint, { ...options, method: 'DELETE' });
  }
}

export const financialClient = new FinancialApiClient();
