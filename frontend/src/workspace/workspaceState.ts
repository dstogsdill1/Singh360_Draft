export type SharedWorkspaceState =
  | 'CLEAN'
  | 'DIRTY'
  | 'PROJECT_SAVED_WORKBOOK_SYNC_PENDING'
  | 'PROJECT_AND_WORKBOOK_MATCH'
  | 'CONFLICT';

export interface WorkspaceStateSignal {
  projectId: string;
  state: SharedWorkspaceState;
  instanceId: string;
  updatedAt: string;
}

const PREFIX = 'singh360:data-workspace:';
const CHANNEL = 'singh360:data-workspace-state';

export function workspaceStateKey(projectId: string): string {
  return `${PREFIX}${projectId}`;
}

export function readWorkspaceState(projectId: string): WorkspaceStateSignal | null {
  try {
    const value = window.localStorage.getItem(workspaceStateKey(projectId));
    if (!value) return null;
    const parsed = JSON.parse(value) as WorkspaceStateSignal;
    return parsed?.projectId === projectId ? parsed : null;
  } catch {
    return null;
  }
}

export function publishWorkspaceState(
  projectId: string,
  state: SharedWorkspaceState,
  instanceId: string,
): WorkspaceStateSignal {
  const signal = { projectId, state, instanceId, updatedAt: new Date().toISOString() };
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
      if (signal?.projectId === projectId) listener(signal);
    };
  } catch {
    channel = null;
  }
  return () => {
    window.removeEventListener('storage', onStorage);
    channel?.close();
  };
}
