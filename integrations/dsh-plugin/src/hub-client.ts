/**
 * Minimal HTTP client for Unifier Hub (mirrors hub/mcp_server/hub_client.py).
 */

export type HubConfig = {
  hubUrl: string
  deviceId: string
  agentId: string
}

export function configFromEnv(cfg?: Partial<HubConfig>): HubConfig {
  const hubUrl = (
    cfg?.hubUrl ??
    process.env.UNIFIER_HUB_URL ??
    process.env.HUB_URL ??
    'http://127.0.0.1:8787'
  ).replace(/\/$/, '')
  const deviceId = cfg?.deviceId ?? process.env.UNIFIER_DEVICE_ID ?? process.env.DEVICE_ID ?? ''
  const agentId = cfg?.agentId ?? process.env.UNIFIER_AGENT_ID ?? process.env.AGENT_ID ?? 'dsh'
  return { hubUrl, deviceId, agentId }
}

export async function hubRequest(
  cfg: HubConfig,
  method: string,
  path: string,
  body?: Record<string, unknown>,
  params?: Record<string, string>,
): Promise<unknown> {
  const url = new URL(path, cfg.hubUrl)
  if (params) {
    for (const [k, v] of Object.entries(params)) url.searchParams.set(k, v)
  }
  const res = await fetch(url, {
    method,
    headers: body ? { 'content-type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  const text = await res.text()
  let data: unknown = text
  try {
    data = text ? JSON.parse(text) : {}
  } catch {
    /* keep text */
  }
  if (!res.ok) {
    throw new Error(`Hub ${res.status}: ${typeof data === 'string' ? data : JSON.stringify(data)}`)
  }
  return data
}

export function pretty(data: unknown): string {
  return JSON.stringify(data, null, 2)
}

export function reviewerId(cfg: HubConfig): string {
  return cfg.deviceId ? `${cfg.deviceId}:${cfg.agentId}` : cfg.agentId
}
