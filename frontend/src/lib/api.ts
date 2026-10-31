import { ApiError, httpFetch, type HttpRequestOptions } from "@/lib/http";

type ApiRequestOptions = Omit<HttpRequestOptions, "method" | "body">;

function errorMessage(body: unknown, status: number): string {
  if (typeof body === "object" && body !== null && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") {
      return detail;
    }
  }

  return `Request failed with status ${status}`;
}

async function parseJsonResponse<T>(response: Response): Promise<T> {
  const text = await response.text();
  let body: unknown;

  if (text === "") {
    body = undefined;
  } else {
    try {
      body = JSON.parse(text) as unknown;
    } catch {
      body = text;
    }
  }

  if (!response.ok) {
    throw new ApiError(errorMessage(body, response.status), {
      status: response.status,
      body,
    });
  }

  return body as T;
}

async function request<T>(
  path: string,
  options: HttpRequestOptions,
): Promise<T> {
  const response = await httpFetch(path, options);
  return parseJsonResponse<T>(response);
}

export const api = {
  get<T>(path: string, options?: ApiRequestOptions): Promise<T> {
    return request<T>(path, { ...options, method: "GET" });
  },

  post<T>(
    path: string,
    body?: unknown,
    options?: ApiRequestOptions,
  ): Promise<T> {
    return request<T>(path, { ...options, method: "POST", body });
  },

  put<T>(
    path: string,
    body?: unknown,
    options?: ApiRequestOptions,
  ): Promise<T> {
    return request<T>(path, { ...options, method: "PUT", body });
  },

  patch<T>(
    path: string,
    body?: unknown,
    options?: ApiRequestOptions,
  ): Promise<T> {
    return request<T>(path, { ...options, method: "PATCH", body });
  },

  delete<T>(path: string, options?: ApiRequestOptions): Promise<T> {
    return request<T>(path, { ...options, method: "DELETE" });
  },
};

export type MeResponse = {
  id: string;
  email: string;
};
