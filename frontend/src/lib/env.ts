type Env = {
  apiBaseUrl: string;
};

function requireEnv(name: string): string {
  const value = import.meta.env[name];

  if (typeof value !== "string" || value.trim() === "") {
    throw new Error(`Missing required environment variable: ${name}`);
  }

  return value.trim();
}

function normalizeBaseUrl(url: string): string {
  if (url === "/") {
    return "";
  }
  return url.endsWith("/") ? url.slice(0, -1) : url;
}

export const env: Env = {
  apiBaseUrl: normalizeBaseUrl(requireEnv("VITE_API_BASE_URL")),
};
