const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

export async function apiGet<T>(path: string): Promise<T> {
  const url = `${BASE_URL}${path}`;
  const res = await fetch(url, { headers: { Accept: "application/json" } });

  if (!res.ok) {
    let code = "HTTP_ERROR";
    let message = res.statusText;
    try {
      const body = await res.json();
      code = body?.error?.code ?? code;
      message = body?.error?.message ?? message;
    } catch {}
    throw new ApiError(res.status, code, message);
  }

  return (await res.json()) as T;
}

export function sseUrl(path: string): string {
  return `${BASE_URL}${path}`;
}
