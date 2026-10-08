import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'
import {
  configFromEnv,
  hubRequest,
  pretty,
  reviewerId,
  type HubConfig,
} from './hub-client.ts'

export type UnifierPluginConfig = {
  hubUrl?: string
  deviceId?: string
  agentId?: string
}

export const name = 'unifier'
export const inject = ['tools']

function cfg(ctx: Context): HubConfig {
  const raw = (ctx.config as UnifierPluginConfig | undefined) ?? {}
  return configFromEnv({
    hubUrl: raw.hubUrl,
    deviceId: raw.deviceId,
    agentId: raw.agentId,
  })
}

export function apply(ctx: Context) {
  const hub = () => cfg(ctx)

  const tools = [
    defineTool({
      name: 'unifier_hub_health',
      description:
        'Check Unifier Hub health. Use before dispatching tasks from DSH (mobile users control via Feishu).',
      parameters: {},
      output: {
        schema: { type: 'string' },
        render: (_a, v) => [{ type: 'text', text: String(v) }],
      },
      async execute() {
        return pretty(await hubRequest(hub(), 'GET', '/health'))
      },
    }),

    defineTool({
      name: 'unifier_whoami',
      description: 'Show DSH plugin identity and Hub URL (device_id used for inbox routing).',
      parameters: {},
      output: {
        schema: { type: 'string' },
        render: (_a, v) => [{ type: 'text', text: String(v) }],
      },
      async execute() {
        const c = hub()
        return pretty({
          hub_url: c.hubUrl,
          device_id: c.deviceId || '(unset — set UNIFIER_DEVICE_ID)',
          agent_id: c.agentId,
          reviewer_id: reviewerId(c),
          mobile_note:
            'Phone users: command via Feishu → Hub; DSH on PC executes and unifier_submit_agent_reply pushes back to Feishu.',
        })
      },
    }),

    defineTool({
      name: 'unifier_dispatch_task',
      description:
        'Create and dispatch a Unifier task (same as Feishu 派活). Mobile user can 派活 in Feishu; DSH can also dispatch from PC.',
      parameters: {
        title: { type: 'string', required: true, description: 'Task title' },
        branch: { type: 'string', description: 'Git branch name' },
        github_owner: { type: 'string', description: 'GitHub owner' },
        github_repo: { type: 'string', description: 'GitHub repo name' },
      },
      output: {
        schema: { type: 'string' },
        render: (_a, v) => [{ type: 'text', text: String(v) }],
      },
      async execute(args) {
        const c = hub()
        const title = String(args.title)
        const data = (await hubRequest(c, 'POST', '/api/v1/orchestrate/dispatch', {
          title,
          branch: args.branch || `feature/dsh-${title.slice(0, 24)}`,
          github_owner: args.github_owner || 'your-org',
          github_repo: args.github_repo || 'your-repo',
          implementer_device_id: c.deviceId,
          implementer_agent_id: c.agentId,
          required_reviewers: [],
          require_connectivity: true,
        })) as { message?: string }
        return data.message ?? pretty(data)
      },
    }),

    defineTool({
      name: 'unifier_get_my_inbox',
      description: 'Fetch inbox for this device+agent (work items and reviews).',
      parameters: {},
      output: {
        schema: { type: 'string' },
        render: (_a, v) => [{ type: 'text', text: String(v) }],
      },
      async execute() {
        const c = hub()
        if (!c.deviceId) throw new Error('Set UNIFIER_DEVICE_ID or plugin config deviceId')
        return pretty(
          await hubRequest(c, 'GET', '/api/v1/tasks/inbox', undefined, {
            device_id: c.deviceId,
            agent_id: c.agentId,
          }),
        )
      },
    }),

    defineTool({
      name: 'unifier_get_task_status',
      description: 'Query task status and review progress (Feishu 状态 N).',
      parameters: {
        task_id: { type: 'string', required: true, description: 'Numeric task id' },
      },
      output: {
        schema: { type: 'string' },
        render: (_a, v) => [{ type: 'text', text: String(v) }],
      },
      async execute(args) {
        const c = hub()
        const id = String(args.task_id)
        const data = (await hubRequest(c, 'GET', `/api/v1/orchestrate/tasks/${id}/status`)) as {
          message?: string
        }
        return data.message ?? pretty(data)
      },
    }),

    defineTool({
      name: 'unifier_check_merge_ready',
      description: 'Check if all reviewers approved (merge_ready).',
      parameters: {
        task_id: { type: 'string', required: true, description: 'Numeric task id' },
      },
      output: {
        schema: { type: 'string' },
        render: (_a, v) => [{ type: 'text', text: String(v) }],
      },
      async execute(args) {
        const c = hub()
        return pretty(await hubRequest(c, 'GET', `/api/v1/tasks/${args.task_id}/merge-ready`))
      },
    }),

    defineTool({
      name: 'unifier_submit_agent_reply',
      description:
        'Push DSH agent reply to Hub and notify Feishu — this is how mobile users see results on phone.',
      parameters: {
        task_id: { type: 'string', required: true, description: 'Numeric task id' },
        content: { type: 'string', required: true, description: 'Reply text for Feishu' },
      },
      output: {
        schema: { type: 'string' },
        render: (_a, v) => [{ type: 'text', text: String(v) }],
      },
      async execute(args) {
        const c = hub()
        if (!c.deviceId) throw new Error('Set UNIFIER_DEVICE_ID')
        const data = await hubRequest(c, 'POST', `/api/v1/tasks/${args.task_id}/agent-replies`, {
          device_id: c.deviceId,
          agent_id: c.agentId,
          content: String(args.content),
          source: 'dsh-plugin',
          notify_feishu: true,
        })
        return `已上报并推送飞书\n${pretty(data)}`
      },
    }),
  ]

  for (const tool of tools) {
    ctx.tools.register(tool)
  }

  console.log(
    `[unifier-dsh-plugin] loaded → ${hub().hubUrl} device=${hub().deviceId || '?'} agent=${hub().agentId}`,
  )
}
