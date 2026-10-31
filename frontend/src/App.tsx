import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { Activity, FleetState, Point, Robot } from './types'

const colors: Record<string, string> = { R1: '#17C3B2', R2: '#E7B45C', R3: '#A5B1C2' }
const API = '/api'

function Warehouse({ state, motionMode }: { state: FleetState; motionMode: 'step' | 'snap' }) {
  const cellW = 78
  const cellH = 72
  const ox = 50
  const oy = 54
  const center = ([x, y]: Point) => [ox + x * cellW + cellW / 2, oy + y * cellH + cellH / 2]
  const floor = new Set(state.layout.floor.map(([x, y]) => `${x}:${y}`))
  const passage = new Set(state.layout.passage.map(([x, y]) => `${x}:${y}`))
  const stationAt = new Map(Object.entries(state.layout.stations).map(([name, point]) => [`${point[0]}:${point[1]}`, name]))
  const reservationOwner = state.robots.find((robot) => robot.id === state.reservation?.owner)
  const staleReservation = !!state.reservation && reservationOwner?.mode !== 'active'

  return (
    <svg className={`warehouse ${motionMode}`} viewBox="0 0 1040 620" role="img" aria-label="Live top-down warehouse simulation">
      <defs>
        <linearGradient id="floor" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#122a3a" />
          <stop offset="1" stopColor="#0c202e" />
        </linearGradient>
        <linearGradient id="passage" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#0c4b50" />
          <stop offset="0.5" stopColor="#126069" />
          <stop offset="1" stopColor="#0c4b50" />
        </linearGradient>
        <filter id="robotShadow" x="-70%" y="-70%" width="240%" height="240%">
          <feDropShadow dx="0" dy="7" stdDeviation="7" floodColor="#02080e" floodOpacity=".65" />
        </filter>
        <filter id="tealGlow" x="-80%" y="-80%" width="260%" height="260%">
          <feGaussianBlur stdDeviation="6" result="blur" />
          <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
        <pattern id="hazard" width="16" height="16" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <rect width="8" height="16" fill="#e4a94b" opacity=".24" />
        </pattern>
      </defs>

      <rect x="14" y="14" width="1012" height="592" rx="22" fill="#081823" stroke="#1b3342" />
      <text x="50" y="36" className="zone-label">WEST OPERATIONS</text>
      <text x="990" y="36" textAnchor="end" className="zone-label">EAST OPERATIONS</text>

      {Array.from({ length: state.layout.height }, (_, y) =>
        Array.from({ length: state.layout.width }, (_, x) => {
          const key = `${x}:${y}`
          const px = ox + x * cellW
          const py = oy + y * cellH
          if (!floor.has(key)) {
            return (
              <g key={key} className="rack">
                <rect x={px + 5} y={py + 4} width={cellW - 10} height={cellH - 8} rx="5" fill="#09141d" stroke="#253947" />
                {[0, 1, 2].map((row) => <line key={row} x1={px + 12} x2={px + cellW - 12} y1={py + 18 + row * 17} y2={py + 18 + row * 17} />)}
                {[0, 1, 2].map((col) => <rect key={col} x={px + 14 + col * 17} y={py + 10} width="11" height="45" rx="2" />)}
              </g>
            )
          }
          const isPassage = passage.has(key)
          const station = stationAt.get(key)
          return (
            <g key={key}>
              <rect x={px + 2} y={py + 2} width={cellW - 4} height={cellH - 4} rx="7"
                fill={isPassage ? 'url(#passage)' : 'url(#floor)'} stroke={isPassage ? '#2bc9be' : '#183849'} strokeWidth={isPassage ? 1.5 : 1} />
              <path d={`M${px + 10} ${py + cellH / 2} H${px + cellW - 10}`} stroke={isPassage ? '#54d9d0' : '#244354'} strokeDasharray="5 8" opacity={isPassage ? .7 : .26} />
              {station && (
                <g>
                  <rect x={px + 10} y={py + 10} width={cellW - 20} height={cellH - 20} rx="9" fill="#153a4a" stroke="#3e6b7c" />
                  <path d={`M${px + 21} ${py + 23}h36v27h-36z M${px + 25} ${py + 27}h28`} fill="none" stroke="#75a6b3" />
                  <text x={px + cellW / 2} y={py + 63} textAnchor="middle" className="station-label">DOCK {station}</text>
                </g>
              )}
            </g>
          )
        }),
      )}

      <g className={state.reservation ? 'reservation active' : 'reservation'}>
        <rect x={ox + 5 * cellW - 5} y={oy + 3 * cellH - 5} width={cellW * 2 + 10} height={cellH + 10} rx="12" fill="none" stroke="#43ddd1" strokeWidth="3" />
        <text x={ox + 6 * cellW} y={oy + 3 * cellH - 16} textAnchor="middle">
          {state.reservation ? `${staleReservation ? 'STALE LOCK' : 'PASSAGE RESERVED'} · ${state.reservation.owner}` : 'SHARED PASSAGE · CLEAR'}
        </text>
      </g>

      {state.robots.map((robot) => {
        const route = [robot.position, ...robot.route.slice(0, 8)].map((point) => center(point).join(',')).join(' ')
        return <polyline key={`route-${robot.id}`} points={route} className="robot-route" style={{ stroke: colors[robot.id] }} />
      })}

      {state.robots.map((robot) => <RobotGlyph key={`${state.sceneId}-${robot.id}`} robot={robot} center={center} />)}

      <g transform="translate(50 583)">
        <circle cx="5" cy="0" r="4" fill="#17C3B2" />
        <text x="18" y="4" className="map-legend">Live engine position</text>
        <line x1="155" x2="181" y1="0" y2="0" stroke="#17C3B2" strokeDasharray="4 5" />
        <text x="191" y="4" className="map-legend">Planned route</text>
        <rect x="320" y="-5" width="10" height="10" rx="2" fill="#e9b45c" />
        <text x="340" y="4" className="map-legend">Payload</text>
      </g>
    </svg>
  )
}

function RobotGlyph({ robot, center }: { robot: Robot; center: (point: Point) => number[] }) {
  const [cx, cy] = center(robot.position)
  const color = colors[robot.id] ?? '#17C3B2'
  const stopped = robot.mode !== 'active'
  const waiting = robot.status.startsWith('waiting')
  const heading = { north: 0, east: 90, south: 180, west: 270, idle: 0 }[robot.heading]
  return (
    <g className={`robot-glyph ${stopped ? 'stopped' : ''} ${waiting ? 'waiting' : ''}`} style={{ transform: `translate(${cx}px, ${cy}px)` }}>
      {stopped && <circle r="34" fill="none" stroke="#f06464" strokeWidth="2" strokeDasharray="5 5" className="incident-ring" />}
      <path d="M0 -29 L-4 -23 H4 Z" fill={stopped ? '#ef6868' : color} transform={`rotate(${heading})`} className="heading-marker" />
      <g filter="url(#robotShadow)">
        <rect x="-23" y="-19" width="46" height="38" rx="13" fill="#0a1720" stroke={stopped ? '#ef6868' : color} strokeWidth="2.5" />
        <rect x="-17" y="-13" width="34" height="22" rx="7" fill={stopped ? '#3b2329' : '#12323d'} />
        <circle cx="-25" cy="-10" r="4" fill="#061018" stroke="#58707d" />
        <circle cx="25" cy="-10" r="4" fill="#061018" stroke="#58707d" />
        <circle cx="-25" cy="10" r="4" fill="#061018" stroke="#58707d" />
        <circle cx="25" cy="10" r="4" fill="#061018" stroke="#58707d" />
        <circle cx="0" cy="-6" r="4" fill={stopped ? '#f06464' : color} className="robot-beacon" />
        <text x="0" y="9" textAnchor="middle" fill="#ecf8fa" fontSize="11" fontWeight="750">{robot.id}</text>
        {robot.carrying && <g transform="translate(12 -25)"><rect x="-8" y="-7" width="17" height="14" rx="2" fill="#dca950" stroke="#ffe0a0" /><path d="M0-7v14M-8-1h17" stroke="#8d672d" /></g>}
      </g>
      <g transform="translate(0 34)">
        <rect x="-34" y="-9" width="68" height="18" rx="9" fill="#07131d" stroke="#284251" />
        <text x="0" y="4" textAnchor="middle" className="robot-status">{stopped ? robot.mode.toUpperCase() : robot.status.replace('waiting: ', '').toUpperCase()}</text>
      </g>
    </g>
  )
}

function activityCopy(item: Activity) {
  const result = item.result
  switch (item.tool) {
    case 'inspect_robots': return ['Fleet scan', 'Checked motion, health, and robot positions.']
    case 'inspect_passage': return ['Passage check', result.physically_empty ? 'Confirmed the shared passage is physically clear.' : 'Detected a robot inside the shared passage.']
    case 'read_recent_events': return ['Event review', 'Reviewed recent movement and incident evidence.']
    case 'inspect_reservations': return ['Reservation audit', result.reservation ? `Found a passage lock owned by ${(result.reservation as { owner: string }).owner}.` : 'Confirmed there is no active passage lock.']
    case 'release_reservation': return [result.ok ? 'Safe lock release' : 'Release blocked', result.ok ? `Released ${(result.released_owner as string)} only after safety checks passed.` : String(result.reason)]
    case 'quarantine_robot': return ['Robot isolated', `Removed ${String(result.robot_id)} from active scheduling.`]
    case 'observe_progress': return ['Recovery observation', `Observed ${String(result.ticks_observed)} ticks · +${String(result.new_deliveries)} deliveries · ${String(result.safety_violations)} safety events.`]
    case 'escalate': return ['Human escalation', 'Automation stopped and requested operator review.']
    default: return [item.tool.replaceAll('_', ' '), 'Recorded by the live recovery agent.']
  }
}

function activityStage(item: Activity) {
  if (item.tool === 'observe_progress') return 'VERIFICATION'
  if (['release_reservation', 'quarantine_robot', 'escalate'].includes(item.tool)) return 'SAFE ACTION'
  if ((item.tool === 'inspect_reservations' && item.result.reservation) || item.tool === 'inspect_passage') return 'DIAGNOSIS'
  return 'INVESTIGATION'
}

function AgentPanel({ state }: { state: FleetState }) {
  const phase = state.result?.status ?? (state.agentRunning ? 'running' : state.injected ? 'incident' : 'standby')
  const evaluation = state.result?.evaluation
  const inactive = state.robots.filter((robot) => robot.mode !== 'active').map((robot) => robot.id)
  const active = state.robots.filter((robot) => robot.mode === 'active').map((robot) => robot.id)
  return (
    <aside className="agent-panel">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">{state.providerMode === 'offline-mock' ? 'OFFLINE RECOVERY FIXTURE' : 'CLAUDE RECOVERY AGENT'}</span>
          <h2>Decision trace</h2>
        </div>
        <span className={`phase-dot ${phase}`}><i />{state.providerMode === 'offline-mock' ? 'Offline mock' : phase === 'complete' ? 'Verified' : phase === 'running' ? 'Working' : phase === 'incident' ? 'Ready' : phase}</span>
      </div>

      <div className="agent-summary">
        <span className="summary-kicker">CURRENT ASSESSMENT</span>
        <strong>{state.agentRunning ? 'Investigating live warehouse state' : state.result?.summary ?? (state.injected ? 'Traffic stalled by an unresolved reservation' : 'System operating normally')}</strong>
        <p>{state.agentRunning ? 'Only validated tools can alter the simulation.' : state.result?.error ?? 'Every decision below comes directly from the agent tool trace.'}</p>
      </div>

      <div className="timeline" aria-live="polite">
        {state.activity.length === 0 && (
          <div className="empty-trace">
            <span className="scan-line" />
            <strong>{state.injected ? 'Incident evidence is ready' : 'Awaiting recovery run'}</strong>
            <p>{state.injected
              ? state.providerMode === 'offline-mock' ? 'Run the offline fixture against the real engine state.' : 'Start the agent to investigate the real engine state.'
              : state.providerMode === 'offline-mock' ? 'Mock tool calls will appear here during offline UI validation.' : 'Tool calls will appear here as Claude makes them.'}</p>
          </div>
        )}
        {state.activity.map((item, index) => {
          const [title, detail] = activityCopy(item)
          const action = ['release_reservation', 'quarantine_robot', 'escalate'].includes(item.tool)
          return (
            <div className={`trace-item ${action ? 'action' : ''}`} key={`${item.call}-${item.tool}`}>
              <div className="trace-index">{String(index + 1).padStart(2, '0')}</div>
              <div><strong>{title}</strong><p>{detail}</p></div>
              <span className="trace-state">{activityStage(item)}</span>
            </div>
          )
        })}
        {state.agentRunning && <div className="trace-item thinking"><div className="trace-index"><i /></div><div><strong>{state.providerMode === 'offline-mock' ? 'Offline fixture is running' : 'Claude is reasoning'}</strong><p>Waiting for the next bounded tool decision.</p></div></div>}
      </div>

      {state.result && (
        <div className={`verification ${state.result.status}`}>
          <div className="verification-title"><span>{state.result.status === 'complete' ? '✓' : '!'}</span><div><small>INDEPENDENT VERIFICATION</small><strong>{state.result.status.toUpperCase()}</strong></div></div>
          {evaluation && <div className="verification-grid"><div><b>+{evaluation.new_deliveries}</b><span>deliveries</span></div><div><b>{evaluation.safety_violations}</b><span>violations</span></div><div><b>{evaluation.healthy_robots_preserved ? 'YES' : 'NO'}</b><span>fleet preserved</span></div></div>}
          {state.result.status === 'complete' && <p className="verification-note">{active.join(' and ')} resumed delivery work. {inactive.length ? `${inactive.join(' and ')} remains safely stationary after failure.` : 'All robots remain active.'}</p>}
          {state.result.modelId && <p className="run-meta">{state.result.modelId} · {state.result.apiAttempts ?? 0} API attempts · ${Number(state.result.estimatedCostUsd ?? 0).toFixed(4)} estimated</p>}
        </div>
      )}
    </aside>
  )
}

function App() {
  const [state, setState] = useState<FleetState | null>(null)
  const [motionMode, setMotionMode] = useState<'step' | 'snap'>('snap')
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const latestVersion = useRef(-1)
  const latestServer = useRef<string | null>(null)
  const latestState = useRef<FleetState | null>(null)

  const request = useCallback(async (path: string, method = 'GET') => {
    const response = await fetch(`${API}${path}`, { method })
    const body = await response.json()
    if (!response.ok) throw new Error(body.detail ?? 'Request failed')
    const next = body as FleetState
    const changedServer = latestServer.current !== null && next.serverId !== latestServer.current
    if (latestServer.current === null || changedServer || next.version >= latestVersion.current) {
      const previous = latestState.current
      const singleEngineStep = !changedServer && !!previous && previous.sceneId === next.sceneId && next.tick - previous.tick <= 1 && next.tick >= previous.tick
      setMotionMode(singleEngineStep ? 'step' : 'snap')
      latestServer.current = next.serverId
      latestVersion.current = next.version
      latestState.current = next
      setState(next)
    }
    return next
  }, [])

  const perform = async (path: string) => {
    setBusy(path)
    setError(null)
    try { await request(path, 'POST') } catch (err) { setError(err instanceof Error ? err.message : 'Request failed') } finally { setBusy(null) }
  }

  useEffect(() => { request('/state').catch(() => setError('FastAPI backend is unavailable.')) }, [request])
  useEffect(() => {
    if (!state) return
    const delay = state.agentRunning ? 250 : state.running ? 180 : 1200
    let cancelled = false
    let timer = 0
    const poll = async () => {
      try { await request('/state'); setError(null) } catch { setError('Connection to the engine was lost.') }
      if (!cancelled) timer = window.setTimeout(poll, delay)
    }
    timer = window.setTimeout(poll, delay)
    return () => { cancelled = true; window.clearTimeout(timer) }
  }, [request, state?.running, state?.agentRunning])

  const phase = useMemo(() => {
    if (!state) return ['CONNECTING', 'neutral']
    if (state.result?.status === 'complete') return ['RECOVERY VERIFIED', 'success']
    if (state.result?.status === 'escalated') return ['HUMAN REVIEW REQUIRED', 'warning']
    if (state.agentRunning) return ['AUTONOMOUS RECOVERY ACTIVE', 'active']
    const owner = state.robots.find((robot) => robot.id === state.reservation?.owner)
    if (state.injected && state.reservation && owner?.mode !== 'active') return ['TRAFFIC INCIDENT', 'danger']
    if (state.running) return ['OPERATIONS LIVE', 'success']
    return ['SYSTEM READY', 'neutral']
  }, [state])

  if (!state) return <div className="loading-screen"><img className="loading-logo" src="/brand/fleetrescue-app-icon.svg" alt="FleetRescue" /><span>Connecting to warehouse engine…</span>{error && <p>{error}</p>}</div>

  const reservationOwner = state.robots.find((robot) => robot.id === state.reservation?.owner)
  const staleReservation = !!state.reservation && reservationOwner?.mode !== 'active'

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand"><img className="brand-logo" src="/brand/fleetrescue-horizontal-reverse.svg" alt="FleetRescue" /></div>
        <div className={`system-phase ${phase[1]}`}><i />{phase[0]}</div>
        <div className="metrics">
          <div><span>SIM TICK</span><strong>{String(state.tick).padStart(3, '0')}</strong></div>
          <div><span>DELIVERIES</span><strong>{state.deliveries}</strong></div>
          <div><span>SAFETY</span><strong className={state.safetyViolations ? 'bad' : ''}>{state.safetyViolations ? `${state.safetyViolations} ALERTS` : 'NOMINAL'}</strong></div>
          <div><span>PASSAGE</span><strong className={staleReservation ? 'bad' : ''}>{state.reservation ? `${staleReservation ? 'STALE' : 'RESERVED'} · ${state.reservation.owner}` : 'AVAILABLE'}</strong></div>
        </div>
      </header>

      <section className="workspace">
        <section className="simulation-panel">
          <div className="simulation-heading"><div><span className="eyebrow">LIVE DIGITAL TWIN</span><h2>Fulfillment floor · Sector 07</h2></div><div className="live-indicator"><i />ENGINE STATE</div></div>
          {state.injected && state.reservation && staleReservation && <div className="incident-banner"><span>!</span><div><small>INCIDENT SCENE LOADED · ENGINE SNAPSHOT</small><strong>STALE RESERVATION DETECTED</strong><p>{state.reservation.owner} is inactive while retaining shared passage access. Healthy traffic is waiting.</p></div><b>{state.reservation.age} TICKS</b></div>}
          <Warehouse key={state.sceneId} state={state} motionMode={motionMode} />
        </section>
        <AgentPanel state={state} />
      </section>

      <footer className="control-bar">
        <div className="control-context"><span>OPERATOR CONTROLS</span><p>Run the deterministic incident sequence, then hand control to the bounded recovery agent.</p></div>
        <div className="controls">
          <button className="primary" onClick={() => perform('/start')} disabled={state.running || state.agentRunning || busy !== null}><span>▶</span>Start Simulation</button>
          <button onClick={() => perform('/fault')} disabled={state.agentRunning || busy !== null}><span>⚠</span>Inject Fault</button>
          <button className="agent-button" onClick={() => perform('/recover')} disabled={!state.injected || state.agentRunning || !!state.result || busy !== null}><span>✦</span>{state.agentRunning ? 'Agent Running' : state.providerMode === 'offline-mock' ? 'Run Mock Recovery' : 'Run Recovery Agent'}</button>
          <button className="icon-button" aria-label="Reset simulation" title="Reset simulation" onClick={() => perform('/reset')} disabled={state.agentRunning || busy !== null}>↻</button>
        </div>
        {error && <div className="toast">{error}</div>}
      </footer>
    </main>
  )
}

export default App
