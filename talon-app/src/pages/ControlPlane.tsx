import { FormEvent, useEffect, useState } from 'react';
import {
  CheckCircle,
  Pause,
  Play,
  ShieldAlert,
  ShieldCheck,
  ShieldX,
  TimerReset,
  XCircle,
} from 'lucide-react';
import { PageHeader, PrototypeNotice, RiskBadge, StatusBadge, SurfaceCard } from '../components/UI';
import { useApp } from '../context/AppContext';
import { RiskLevel, ScheduledJobRun } from '../types';

export default function ControlPlane() {
  const {
    employees,
    hitlRequests,
    pauseEmployee,
    resumeEmployee,
    approveHitl,
    rejectHitl,
    createHitl,
    policyRules,
    togglePolicyRule,
    scheduledJobs,
    createScheduledJob,
    pauseScheduledJob,
    resumeScheduledJob,
    runScheduledJobNow,
    loadScheduledJobRuns,
    checkpoints,
    createCheckpoint,
    restoreCheckpoint,
    systemHealth,
    setKillSwitch,
    isLoading,
  } = useApp();
  const [agentId, setAgentId] = useState('');
  const [task, setTask] = useState('');
  const [reason, setReason] = useState('');
  const [riskLevel, setRiskLevel] = useState<RiskLevel>('medium');
  const [requestedBy, setRequestedBy] = useState('dashboard-operator');
  const [scheduleAgentId, setScheduleAgentId] = useState('');
  const [scheduleName, setScheduleName] = useState('');
  const [schedulePrompt, setSchedulePrompt] = useState('');
  const [intervalMinutes, setIntervalMinutes] = useState(60);
  const [startImmediately, setStartImmediately] = useState(false);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [selectedJobRuns, setSelectedJobRuns] = useState<ScheduledJobRun[]>([]);
  const [jobRunsError, setJobRunsError] = useState<string | null>(null);
  const [checkpointAgentId, setCheckpointAgentId] = useState('');
  const [checkpointLabel, setCheckpointLabel] = useState('');
  const [checkpointSummary, setCheckpointSummary] = useState('');
  const [checkpointCreatedBy, setCheckpointCreatedBy] = useState('dashboard-operator');
  const [killSwitchReason, setKillSwitchReason] = useState('');
  const [killSwitchUpdatedBy, setKillSwitchUpdatedBy] = useState('dashboard-operator');

  useEffect(() => {
    if (!selectedJobId) {
      setSelectedJobRuns([]);
      setJobRunsError(null);
      return;
    }

    let cancelled = false;

    async function refreshRuns() {
      try {
        const runs = await loadScheduledJobRuns(selectedJobId, 10);
        if (!cancelled) {
          setSelectedJobRuns(runs);
          setJobRunsError(null);
        }
      } catch (error) {
        if (!cancelled) {
          setSelectedJobRuns([]);
          setJobRunsError(error instanceof Error ? error.message : 'Failed to load job runs');
        }
      }
    }

    void refreshRuns();
    return () => {
      cancelled = true;
    };
  }, [selectedJobId, loadScheduledJobRuns, scheduledJobs]);

  async function handleHitlSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!agentId || !task.trim() || !reason.trim()) {
      return;
    }

    await createHitl({
      agentId,
      task: task.trim(),
      reason: reason.trim(),
      riskLevel,
      requestedBy: requestedBy.trim() || undefined,
    });

    setTask('');
    setReason('');
  }

  async function handleScheduleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!scheduleAgentId || !scheduleName.trim() || !schedulePrompt.trim()) {
      return;
    }

    await createScheduledJob({
      agentId: scheduleAgentId,
      name: scheduleName.trim(),
      prompt: schedulePrompt.trim(),
      intervalMinutes,
      startImmediately,
    });

    setScheduleName('');
    setSchedulePrompt('');
    setIntervalMinutes(60);
    setStartImmediately(false);
  }

  async function handleCheckpointSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!checkpointAgentId || !checkpointLabel.trim()) {
      return;
    }

    await createCheckpoint({
      agentId: checkpointAgentId,
      label: checkpointLabel.trim(),
      summary: checkpointSummary.trim(),
      createdBy: checkpointCreatedBy.trim() || undefined,
    });

    setCheckpointLabel('');
    setCheckpointSummary('');
  }

  return (
    <div>
      <PageHeader
        title="Control Plane"
        subtitle="Pause/resume, HITL, policy controls, recurring scheduled jobs, checkpoints, and the global kill switch are backed by real APIs."
      />

      <div className="mb-6 grid grid-cols-1 gap-4 xl:grid-cols-3">
        <PrototypeNotice
          title="What is live right now"
          description="Agent pause/resume, HITL request approvals, backend-managed policy rules, recurring scheduled jobs, per-agent checkpoints, and the global kill switch are backed by real APIs and persisted in SQLite."
        />
        <PrototypeNotice
          title="What is still roadmap work"
          description={
            systemHealth.policyEngine?.engine === 'opa'
              ? `OPA/Rego evaluation is active. ${systemHealth.policyEngine.detail}`
              : 'OPA/Rego evaluation is now supported when the backend is configured with POLICY_ENGINE=opa and OPA_BASE_URL.'
          }
        />
        <SurfaceCard className="p-4">
          <div className="text-sm font-semibold text-white">Queue Snapshot</div>
          <div className="mt-3 space-y-2 text-sm text-slate-300">
            <div className="flex items-center justify-between">
              <span>Pending HITL</span>
              <span>{hitlRequests.filter((request) => request.status === 'pending').length}</span>
            </div>
            <div className="flex items-center justify-between">
              <span>Active schedules</span>
              <span>{scheduledJobs.filter((job) => job.status === 'active').length}</span>
            </div>
            <div className="flex items-center justify-between">
              <span>Paused schedules</span>
              <span>{scheduledJobs.filter((job) => job.status === 'paused').length}</span>
            </div>
            <div className="flex items-center justify-between">
              <span>Checkpoints</span>
              <span>{checkpoints.length}</span>
            </div>
            <div className="flex items-center justify-between">
              <span>Kill switch</span>
              <span>{systemHealth.killSwitch.active ? 'active' : 'off'}</span>
            </div>
          </div>
        </SurfaceCard>
      </div>

      <SurfaceCard className={`mb-6 p-5 ${systemHealth.killSwitch.active ? 'border-red-500/40 bg-red-500/10' : ''}`}>
        <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold text-white">
          <ShieldAlert className={`h-4 w-4 ${systemHealth.killSwitch.active ? 'text-red-400' : 'text-slate-400'}`} />
          Global Kill Switch
        </h2>
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1.2fr_0.8fr]">
          <div className="space-y-3">
            <div className="text-sm text-slate-300">
              {systemHealth.killSwitch.active
                ? 'New agent work is currently halted across web chat, Teams, direct-message tests, and scheduled jobs.'
                : 'When activated, the kill switch blocks new work across all execution entrypoints without deleting agent state.'}
            </div>
            {systemHealth.killSwitch.active && (
              <div className="rounded-xl border border-red-500/30 bg-slate-950/70 p-4 text-sm text-slate-300">
                <div className="font-semibold text-red-300">Current reason</div>
                <div className="mt-1">{systemHealth.killSwitch.reason || 'No reason recorded.'}</div>
                <div className="mt-2 text-xs text-slate-500">
                  {systemHealth.killSwitch.activatedAt
                    ? `Activated ${systemHealth.killSwitch.activatedAt.toLocaleString()}`
                    : 'Activation time unavailable'}
                  {systemHealth.killSwitch.updatedBy ? ` by ${systemHealth.killSwitch.updatedBy}` : ''}
                </div>
              </div>
            )}
          </div>

          <div className="space-y-3">
            <label className="block">
              <span className="mb-2 block text-xs font-medium uppercase tracking-wide text-slate-400">Reason</span>
              <textarea
                value={killSwitchReason}
                onChange={(event) => setKillSwitchReason(event.target.value)}
                className="min-h-24 w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm text-slate-100 outline-none focus:border-blue-500"
                placeholder="Incident response, maintenance window, or emergency stop reason."
              />
            </label>
            <label className="block">
              <span className="mb-2 block text-xs font-medium uppercase tracking-wide text-slate-400">Updated By</span>
              <input
                value={killSwitchUpdatedBy}
                onChange={(event) => setKillSwitchUpdatedBy(event.target.value)}
                className="w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm text-slate-100 outline-none focus:border-blue-500"
              />
            </label>
            <div className="flex flex-wrap gap-2">
              <button
                onClick={() =>
                  void setKillSwitch({
                    active: true,
                    reason: killSwitchReason.trim(),
                    updatedBy: killSwitchUpdatedBy.trim() || undefined,
                  })
                }
                disabled={isLoading || systemHealth.killSwitch.active}
                className="rounded-xl bg-red-600 px-4 py-3 text-sm font-semibold text-white transition-colors hover:bg-red-500 disabled:opacity-60"
              >
                Activate Kill Switch
              </button>
              <button
                onClick={() =>
                  void setKillSwitch({
                    active: false,
                    reason: '',
                    updatedBy: killSwitchUpdatedBy.trim() || undefined,
                  })
                }
                disabled={isLoading || !systemHealth.killSwitch.active}
                className="rounded-xl bg-slate-700 px-4 py-3 text-sm font-semibold text-slate-100 transition-colors hover:bg-slate-600 disabled:opacity-60"
              >
                Clear Kill Switch
              </button>
            </div>
          </div>
        </div>
      </SurfaceCard>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <SurfaceCard className="p-5">
          <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold text-white">
            <ShieldCheck className="h-4 w-4 text-blue-400" />
            Agent Controls
          </h2>
          <div className="space-y-3">
            {employees.map((employee) => (
              <div key={employee.id} className="rounded-xl border border-slate-700/50 bg-slate-900/50 p-4">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <div
                      className="flex h-10 w-10 items-center justify-center rounded-2xl border text-lg"
                      style={{ borderColor: `${employee.color}50`, backgroundColor: `${employee.color}18` }}
                    >
                      {employee.emoji}
                    </div>
                    <div>
                      <div className="font-semibold text-white">{employee.name}</div>
                      <div className="text-xs" style={{ color: employee.color }}>
                        {employee.role}
                      </div>
                    </div>
                  </div>
                  <StatusBadge status={employee.status} />
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    onClick={() => void (employee.status === 'active' ? pauseEmployee(employee.id) : resumeEmployee(employee.id))}
                    disabled={isLoading}
                    className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-500 disabled:opacity-60"
                  >
                    {employee.status === 'active' ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
                    {employee.status === 'active' ? 'Pause' : 'Resume'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </SurfaceCard>

        <SurfaceCard className="p-5">
          <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold text-white">
            <ShieldAlert className="h-4 w-4 text-yellow-400" />
            Create HITL Request
          </h2>
          <form className="space-y-4" onSubmit={(event) => void handleHitlSubmit(event)}>
            <label className="block">
              <span className="mb-2 block text-xs font-medium uppercase tracking-wide text-slate-400">Agent</span>
              <select
                value={agentId}
                onChange={(event) => setAgentId(event.target.value)}
                className="w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm text-slate-100 outline-none focus:border-blue-500"
                required
              >
                <option value="">Select an agent</option>
                {employees.map((employee) => (
                  <option key={employee.id} value={employee.id}>
                    {employee.name}
                  </option>
                ))}
              </select>
            </label>

            <label className="block">
              <span className="mb-2 block text-xs font-medium uppercase tracking-wide text-slate-400">Task</span>
              <input
                value={task}
                onChange={(event) => setTask(event.target.value)}
                className="w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm text-slate-100 outline-none focus:border-blue-500"
                placeholder="Drain node after confirming replacement capacity"
                required
              />
            </label>

            <label className="block">
              <span className="mb-2 block text-xs font-medium uppercase tracking-wide text-slate-400">Reason</span>
              <textarea
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                className="min-h-28 w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm text-slate-100 outline-none focus:border-blue-500"
                placeholder="Explain why a human decision is required before execution."
                required
              />
            </label>

            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <label className="block">
                <span className="mb-2 block text-xs font-medium uppercase tracking-wide text-slate-400">Risk</span>
                <select
                  value={riskLevel}
                  onChange={(event) => setRiskLevel(event.target.value as RiskLevel)}
                  className="w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm text-slate-100 outline-none focus:border-blue-500"
                >
                  {(['low', 'medium', 'high', 'critical'] as const).map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
              </label>

              <label className="block">
                <span className="mb-2 block text-xs font-medium uppercase tracking-wide text-slate-400">Requested By</span>
                <input
                  value={requestedBy}
                  onChange={(event) => setRequestedBy(event.target.value)}
                  className="w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm text-slate-100 outline-none focus:border-blue-500"
                />
              </label>
            </div>

            <button
              type="submit"
              disabled={isLoading}
              className="rounded-xl bg-blue-600 px-4 py-3 text-sm font-semibold text-white transition-colors hover:bg-blue-500 disabled:opacity-60"
            >
              Submit HITL Request
            </button>
          </form>
        </SurfaceCard>
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-2">
        <SurfaceCard className="p-5">
          <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold text-white">
            <TimerReset className="h-4 w-4 text-green-400" />
            Create Scheduled Job
          </h2>
          <form className="space-y-4" onSubmit={(event) => void handleScheduleSubmit(event)}>
            <label className="block">
              <span className="mb-2 block text-xs font-medium uppercase tracking-wide text-slate-400">Agent</span>
              <select
                value={scheduleAgentId}
                onChange={(event) => setScheduleAgentId(event.target.value)}
                className="w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm text-slate-100 outline-none focus:border-blue-500"
                required
              >
                <option value="">Select an agent</option>
                {employees.map((employee) => (
                  <option key={employee.id} value={employee.id}>
                    {employee.name}
                  </option>
                ))}
              </select>
            </label>

            <label className="block">
              <span className="mb-2 block text-xs font-medium uppercase tracking-wide text-slate-400">Job Name</span>
              <input
                value={scheduleName}
                onChange={(event) => setScheduleName(event.target.value)}
                className="w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm text-slate-100 outline-none focus:border-blue-500"
                placeholder="Daily queue digest"
                required
              />
            </label>

            <label className="block">
              <span className="mb-2 block text-xs font-medium uppercase tracking-wide text-slate-400">Prompt</span>
              <textarea
                value={schedulePrompt}
                onChange={(event) => setSchedulePrompt(event.target.value)}
                className="min-h-28 w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm text-slate-100 outline-none focus:border-blue-500"
                placeholder="Check the incident queue and summarize anything that needs follow-up."
                required
              />
            </label>

            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <label className="block">
                <span className="mb-2 block text-xs font-medium uppercase tracking-wide text-slate-400">Interval (minutes)</span>
                <input
                  type="number"
                  min={1}
                  value={intervalMinutes}
                  onChange={(event) => setIntervalMinutes(Number(event.target.value))}
                  className="w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm text-slate-100 outline-none focus:border-blue-500"
                  required
                />
              </label>

              <label className="flex items-center gap-3 rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm text-slate-300">
                <input
                  type="checkbox"
                  checked={startImmediately}
                  onChange={(event) => setStartImmediately(event.target.checked)}
                  className="h-4 w-4 rounded border-slate-600 bg-slate-900"
                />
                Run immediately after creation
              </label>
            </div>

            <button
              type="submit"
              disabled={isLoading}
              className="rounded-xl bg-green-600 px-4 py-3 text-sm font-semibold text-white transition-colors hover:bg-green-500 disabled:opacity-60"
            >
              Create Scheduled Job
            </button>
          </form>
        </SurfaceCard>

        <SurfaceCard className="p-5">
          <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold text-white">
            <ShieldX className="h-4 w-4 text-purple-400" />
            Active Policy Rules
          </h2>
          <div className="space-y-3">
            {policyRules.map((rule) => (
              <div key={rule.id} className="rounded-xl border border-slate-700/50 bg-slate-900/50 p-4">
                <div className="mb-2 flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold text-white">{rule.name}</div>
                    <div className="text-xs text-slate-500">
                      {rule.scope} · priority {rule.priority}
                    </div>
                  </div>
                  <button
                    onClick={() => void togglePolicyRule(rule.id, !rule.enabled)}
                    disabled={isLoading}
                    className={`rounded-lg px-3 py-2 text-xs font-medium transition-colors ${
                      rule.enabled
                        ? 'bg-green-500/15 text-green-300 hover:bg-green-500/25'
                        : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                    }`}
                  >
                    {rule.enabled ? 'Enabled' : 'Disabled'}
                  </button>
                </div>
                <div className="mb-2 text-sm text-slate-300">{rule.description}</div>
                <code className="block overflow-x-auto rounded-lg bg-slate-950 px-3 py-2 text-xs text-slate-400">
                  {rule.pattern}
                </code>
              </div>
            ))}
          </div>
        </SurfaceCard>
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-2">
        <SurfaceCard className="p-5">
          <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold text-white">
            <ShieldCheck className="h-4 w-4 text-cyan-400" />
            Create Checkpoint
          </h2>
          <form className="space-y-4" onSubmit={(event) => void handleCheckpointSubmit(event)}>
            <label className="block">
              <span className="mb-2 block text-xs font-medium uppercase tracking-wide text-slate-400">Agent</span>
              <select
                value={checkpointAgentId}
                onChange={(event) => setCheckpointAgentId(event.target.value)}
                className="w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm text-slate-100 outline-none focus:border-blue-500"
                required
              >
                <option value="">Select an agent</option>
                {employees.map((employee) => (
                  <option key={employee.id} value={employee.id}>
                    {employee.name}
                  </option>
                ))}
              </select>
            </label>

            <label className="block">
              <span className="mb-2 block text-xs font-medium uppercase tracking-wide text-slate-400">Checkpoint Label</span>
              <input
                value={checkpointLabel}
                onChange={(event) => setCheckpointLabel(event.target.value)}
                className="w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm text-slate-100 outline-none focus:border-blue-500"
                placeholder="Before queue reclassification rollout"
                required
              />
            </label>

            <label className="block">
              <span className="mb-2 block text-xs font-medium uppercase tracking-wide text-slate-400">Summary</span>
              <textarea
                value={checkpointSummary}
                onChange={(event) => setCheckpointSummary(event.target.value)}
                className="min-h-24 w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm text-slate-100 outline-none focus:border-blue-500"
                placeholder="Optional note about why this snapshot matters."
              />
            </label>

            <label className="block">
              <span className="mb-2 block text-xs font-medium uppercase tracking-wide text-slate-400">Created By</span>
              <input
                value={checkpointCreatedBy}
                onChange={(event) => setCheckpointCreatedBy(event.target.value)}
                className="w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm text-slate-100 outline-none focus:border-blue-500"
              />
            </label>

            <button
              type="submit"
              disabled={isLoading}
              className="rounded-xl bg-cyan-600 px-4 py-3 text-sm font-semibold text-white transition-colors hover:bg-cyan-500 disabled:opacity-60"
            >
              Create Checkpoint
            </button>
          </form>
        </SurfaceCard>

        <SurfaceCard className="p-5">
          <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold text-white">
            <ShieldAlert className="h-4 w-4 text-cyan-400" />
            Available Checkpoints
          </h2>
          <div className="space-y-3">
            {checkpoints.length === 0 && <p className="text-sm text-slate-400">No checkpoints created yet.</p>}
            {checkpoints.map((checkpoint) => (
              <div key={checkpoint.id} className="rounded-xl border border-slate-700/50 bg-slate-900/50 p-4">
                <div className="mb-2 flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold text-white">{checkpoint.label}</div>
                    <div className="text-xs text-slate-500">
                      {checkpoint.agentName} · {checkpoint.createdAt.toLocaleString()}
                    </div>
                  </div>
                  <button
                    onClick={() =>
                      void restoreCheckpoint(checkpoint.id, {
                        createdBy: checkpointCreatedBy.trim() || undefined,
                        createSafetyCheckpoint: true,
                      })
                    }
                    disabled={isLoading}
                    className="rounded-lg bg-cyan-600 px-3 py-2 text-xs font-medium text-white transition-colors hover:bg-cyan-500 disabled:opacity-60"
                  >
                    Restore
                  </button>
                </div>
                {checkpoint.summary && <div className="mb-3 text-sm text-slate-300">{checkpoint.summary}</div>}
                <div className="grid grid-cols-2 gap-2 text-xs text-slate-500 md:grid-cols-5">
                  <div>Convos: {checkpoint.stats.conversations}</div>
                  <div>Episodic: {checkpoint.stats.episodicMemories}</div>
                  <div>Entities: {checkpoint.stats.entityRecords}</div>
                  <div>HITL: {checkpoint.stats.hitlRequests}</div>
                  <div>Schedules: {checkpoint.stats.scheduledJobs}</div>
                </div>
              </div>
            ))}
          </div>
        </SurfaceCard>
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <SurfaceCard className="p-5">
          <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold text-white">
            <TimerReset className="h-4 w-4 text-green-400" />
            Scheduled Jobs
          </h2>
          <div className="space-y-3">
            {scheduledJobs.length === 0 && <p className="text-sm text-slate-400">No scheduled jobs yet.</p>}
            {scheduledJobs.map((job) => (
              <button
                key={job.id}
                onClick={() => setSelectedJobId(job.id)}
                className={`w-full rounded-xl border p-4 text-left transition-colors ${
                  selectedJobId === job.id
                    ? 'border-green-500/40 bg-green-500/10'
                    : 'border-slate-700/50 bg-slate-900/50 hover:border-slate-600'
                }`}
              >
                <div className="mb-2 flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold text-white">{job.name}</div>
                    <div className="text-xs text-slate-500">
                      {job.agentName} · every {job.intervalMinutes} min
                    </div>
                  </div>
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                      job.status === 'active'
                        ? 'bg-green-500/15 text-green-300'
                        : job.status === 'running'
                          ? 'bg-blue-500/15 text-blue-300'
                          : 'bg-slate-700 text-slate-300'
                    }`}
                  >
                    {job.status}
                  </span>
                </div>
                <div className="mb-3 text-sm text-slate-300">{job.prompt}</div>
                <div className="grid grid-cols-1 gap-2 text-xs text-slate-500 md:grid-cols-2">
                  <div>Next run: {job.nextRunAt ? job.nextRunAt.toLocaleString() : 'not scheduled'}</div>
                  <div>Last run: {job.lastRunAt ? job.lastRunAt.toLocaleString() : 'never'}</div>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={(event) => {
                      event.stopPropagation();
                      void runScheduledJobNow(job.id);
                    }}
                    disabled={isLoading}
                    className="rounded-lg bg-green-600 px-3 py-2 text-xs font-medium text-white transition-colors hover:bg-green-500 disabled:opacity-60"
                  >
                    Run now
                  </button>
                  <button
                    type="button"
                    onClick={(event) => {
                      event.stopPropagation();
                      void (job.status === 'paused' ? resumeScheduledJob(job.id) : pauseScheduledJob(job.id));
                    }}
                    disabled={isLoading}
                    className="rounded-lg bg-slate-700 px-3 py-2 text-xs font-medium text-slate-200 transition-colors hover:bg-slate-600 disabled:opacity-60"
                  >
                    {job.status === 'paused' ? 'Resume' : 'Pause'}
                  </button>
                </div>
                {job.lastError && <div className="mt-3 text-xs text-red-400">Last error: {job.lastError}</div>}
                {job.lastResult && !job.lastError && (
                  <div className="mt-3 text-xs text-slate-400">Last result: {job.lastResult}</div>
                )}
              </button>
            ))}
          </div>
        </SurfaceCard>

        <SurfaceCard className="p-5">
          <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold text-white">
            <TimerReset className="h-4 w-4 text-blue-400" />
            Recent Job Runs
          </h2>
          {jobRunsError && <p className="mb-3 text-sm text-red-400">{jobRunsError}</p>}
          {!selectedJobId && <p className="text-sm text-slate-400">Select a scheduled job to inspect recent runs.</p>}
          <div className="space-y-3">
            {selectedJobRuns.map((run) => (
              <div key={run.id} className="rounded-xl border border-slate-700/50 bg-slate-900/50 p-4">
                <div className="mb-2 flex items-center justify-between gap-3">
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                      run.status === 'success'
                        ? 'bg-green-500/15 text-green-300'
                        : run.status === 'skipped'
                          ? 'bg-yellow-500/15 text-yellow-300'
                          : 'bg-red-500/15 text-red-300'
                    }`}
                  >
                    {run.status}
                  </span>
                  <span className="text-xs text-slate-500">{run.startedAt.toLocaleString()}</span>
                </div>
                {run.responsePreview && <div className="text-sm text-slate-300">{run.responsePreview}</div>}
                {run.error && <div className="text-sm text-red-400">{run.error}</div>}
                {run.conversationId && <div className="mt-2 text-xs text-slate-500">Conversation: {run.conversationId}</div>}
              </div>
            ))}
          </div>
        </SurfaceCard>
      </div>

      <SurfaceCard className="mt-6 p-5">
        <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold text-white">
          <ShieldAlert className="h-4 w-4 text-orange-400" />
          HITL Queue
        </h2>
        <div className="space-y-3">
          {hitlRequests.length === 0 && <p className="text-sm text-slate-400">No HITL requests yet.</p>}
          {hitlRequests.map((request) => (
            <div key={request.id} className="rounded-xl border border-slate-700/50 bg-slate-900/50 p-4">
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <div className="text-sm font-semibold text-white">{request.employeeName}</div>
                <RiskBadge level={request.riskLevel} />
                <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${request.status === 'approved' ? 'bg-green-500/15 text-green-300' : request.status === 'rejected' ? 'bg-red-500/15 text-red-300' : 'bg-yellow-500/15 text-yellow-300'}`}>
                  {request.status}
                </span>
              </div>
              <div className="text-sm text-slate-100">{request.task}</div>
              <div className="mt-1 text-sm text-slate-400">{request.reason}</div>
              <div className="mt-2 text-xs text-slate-500">
                Requested {request.timestamp.toLocaleString()}
                {request.requestedBy ? ` by ${request.requestedBy}` : ''}
              </div>
              {request.note && <div className="mt-2 text-xs text-slate-500">Decision note: {request.note}</div>}

              {request.status === 'pending' && (
                <div className="mt-4 flex flex-wrap gap-2">
                  <button
                    onClick={() => void approveHitl(request.id)}
                    className="inline-flex items-center gap-2 rounded-lg bg-green-600 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-green-500"
                  >
                    <CheckCircle className="h-4 w-4" />
                    Approve
                  </button>
                  <button
                    onClick={() => void rejectHitl(request.id)}
                    className="inline-flex items-center gap-2 rounded-lg bg-red-600 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-red-500"
                  >
                    <XCircle className="h-4 w-4" />
                    Reject
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      </SurfaceCard>
    </div>
  );
}
