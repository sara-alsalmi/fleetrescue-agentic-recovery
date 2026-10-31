export type Point = [number, number]

export interface Robot {
  id: string
  position: Point
  mode: 'active' | 'inactive' | 'quarantined'
  status: string
  carrying: boolean
  deliveries: number
  route: Point[]
  heading: 'north' | 'south' | 'east' | 'west' | 'idle'
  motionlessTicks: number
}

export interface Activity {
  call: number
  tool: string
  args: Record<string, unknown>
  result: Record<string, unknown>
}

export interface Evaluation {
  outcome: string
  new_deliveries: number
  safety_violations: number
  healthy_robots_preserved: boolean
  legitimate_reservations_preserved: boolean
  input_tokens: number
  output_tokens: number
}

export interface AgentResult {
  status: string
  summary: string
  inputTokens?: number
  outputTokens?: number
  error?: string | null
  evaluation?: Evaluation | null
  modelId?: string | null
  apiAttempts?: number
  estimatedCostUsd?: number
  costCeilingUsd?: number
}

export interface FleetState {
  serverId: string
  version: number
  sceneId: number
  sceneReason: 'initial' | 'reset' | 'fault'
  providerMode: 'live' | 'offline-mock'
  tick: number
  running: boolean
  injected: boolean
  agentRunning: boolean
  deliveries: number
  safetyViolations: number
  escalated: boolean
  reservation: { owner: string; age: number } | null
  incidentPosition: Point | null
  robots: Robot[]
  activity: Activity[]
  result: AgentResult | null
  layout: {
    width: number
    height: number
    passage: Point[]
    stations: Record<string, Point>
    floor: Point[]
  }
}
