import { env } from "@/lib/env";
import { accessToken } from "@/lib/auth-token";

const DEFAULT_TIMEOUT_MS = 30_000;

export type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export type HttpRequestOptions = {
  method?: HttpMethod;
  body?: unknown;
  headers?: Record<string, string>;
  timeoutMs?: number;
  auth?: boolean;
};

export class ApiError extends Error {
  readonly status: number;
  readonly isNetworkError: boolean;
  readonly body: unknown;

  constructor(
    message: string,
    options: { status: number; isNetworkError?: boolean; body?: unknown },
  ) {
    super(message);
    this.name = "ApiError";
    this.status = options.status;
    this.isNetworkError = options.isNetworkError ?? false;
    this.body = options.body;
  }
}

function buildUrl(path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }

  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  if (
    env.apiBaseUrl &&
    (normalizedPath === env.apiBaseUrl ||
      normalizedPath.startsWith(`${env.apiBaseUrl}/`))
  ) {
    return normalizedPath;
  }
  return `${env.apiBaseUrl}${normalizedPath}`;
}

export { accessToken } from "@/lib/auth-token";

export async function httpFetch(
  path: string,
  options: HttpRequestOptions = {},
): Promise<Response> {
  const {
    method = "GET",
    body,
    headers = {},
    timeoutMs = DEFAULT_TIMEOUT_MS,
    auth = true,
  } = options;

  const requestHeaders = new Headers(headers);

  if (body !== undefined && !requestHeaders.has("Content-Type")) {
    requestHeaders.set("Content-Type", "application/json");
  }

  if (auth) {
    const token = await accessToken();
    if (token) {
      requestHeaders.set("Authorization", `Bearer ${token}`);
    }
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  try {
    return await fetch(buildUrl(path), {
      method,
      headers: requestHeaders,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError("Request timed out", {
        status: 0,
        isNetworkError: true,
      });
    }

    throw new ApiError("Network error", { status: 0, isNetworkError: true });
  } finally {
    clearTimeout(timeout);
  }
}
