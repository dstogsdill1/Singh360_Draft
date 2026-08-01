export type SharedWorkspaceState =
  | 'CLEAN'
  | 'DIRTY'
  | 'CONFLICT';

export interface WorkspaceStateSignal {
  projectId: string;
  state: SharedWorkspaceState;
  instanceId: string;
  updatedAt: string;
  expiresAt: string;
  revision: number;
  signature: string;
  dirtyDomains: string[];
}

const PREFIX = 'singh360:data-workspace:';
const CHANNEL = 'singh360:data-workspace-state';
const LEASE_MS = 30_000;

export function workspaceStateKey(projectId: string): string {
  return `${PREFIX}${projectId}`;
}

export function readWorkspaceState(projectId: string): WorkspaceStateSignal | null {
  try {
    const value = window.localStorage.getItem(workspaceStateKey(projectId));
    if (!value) return null;
    const parsed = JSON.parse(value) as WorkspaceStateSignal;
    if (parsed?.projectId !== projectId) return null;
    if (
      (parsed.state === 'DIRTY' || parsed.state === 'CONFLICT')
      && (!parsed.expiresAt || Date.parse(parsed.expiresAt) <= Date.now())
    ) {
      window.localStorage.removeItem(workspaceStateKey(projectId));
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

export function publishWorkspaceState(
  projectId: string,
  state: SharedWorkspaceState,
  instanceId: string,
  details: { revision?: number; signature?: string; dirtyDomains?: string[] } = {},
): WorkspaceStateSignal {
  const now = new Date();
  const signal = {
    projectId,
    state,
    instanceId,
    updatedAt: now.toISOString(),
    expiresAt: new Date(now.getTime() + LEASE_MS).toISOString(),
    revision: details.revision || 0,
    signature: details.signature || '',
    dirtyDomains: details.dirtyDomains || [],
  };
  window.localStorage.setItem(workspaceStateKey(projectId), JSON.stringify(signal));
  try {
    const channel = new BroadcastChannel(CHANNEL);
    channel.postMessage(signal);
    channel.close();
  } catch {
    // The storage event remains the cross-window fallback.
  }
  return signal;
}

export function subscribeWorkspaceState(
  projectId: string,
  listener: (signal: WorkspaceStateSignal | null) => void,
): () => void {
  const onStorage = (event: StorageEvent) => {
    if (event.key === workspaceStateKey(projectId)) listener(readWorkspaceState(projectId));
  };
  window.addEventListener('storage', onStorage);
  let channel: BroadcastChannel | null = null;
  try {
    channel = new BroadcastChannel(CHANNEL);
    channel.onmessage = (event) => {
      const signal = event.data as WorkspaceStateSignal;
      if (signal?.projectId !== projectId) return;
      if (
        (signal.state === 'DIRTY' || signal.state === 'CONFLICT')
        && (!signal.expiresAt || Date.parse(signal.expiresAt) <= Date.now())
      ) listener(null);
      else listener(signal);
    };
  } catch {
    channel = null;
  }
  return () => {
    window.removeEventListener('storage', onStorage);
    channel?.close();
  };
}
