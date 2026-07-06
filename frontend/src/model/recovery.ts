import type { ProjectModel } from './types';

// Local (browser) recovery snapshots. After every canvas change we stash the
// project overlay state so a crash/refresh/failed-save can be recovered even if
// the server never persisted it. Keep the last 10 snapshots per project.

export interface RecoverySnapshot {
  projectId: string;
  savedAt: string; // ISO
  project: ProjectModel;
}

const MAX_SNAPSHOTS = 10;
const keyFor = (projectId: string) => `singh360:recovery:${projectId}`;

export function writeRecoverySnapshot(project: ProjectModel): void {
  if (!project?.id) return;
  const key = keyFor(project.id);
  const snapshot: RecoverySnapshot = {
    projectId: project.id,
    savedAt: new Date().toISOString(),
    project,
  };
  try {
    const list = listRecoverySnapshots(project.id);
    list.push(snapshot);
    while (list.length > MAX_SNAPSHOTS) list.shift();
    localStorage.setItem(key, JSON.stringify(list));
  } catch {
    // Quota exceeded or storage disabled — drop older snapshots and retry once.
    try {
      localStorage.setItem(key, JSON.stringify([snapshot]));
    } catch {
      /* ignore — recovery is best-effort */
    }
  }
}

export function listRecoverySnapshots(projectId: string): RecoverySnapshot[] {
  try {
    const raw = localStorage.getItem(keyFor(projectId));
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as RecoverySnapshot[]) : [];
  } catch {
    return [];
  }
}

export function latestRecoverySnapshot(projectId: string): RecoverySnapshot | null {
  const list = listRecoverySnapshots(projectId);
  return list.length ? list[list.length - 1] : null;
}

export function clearRecoverySnapshots(projectId: string): void {
  try {
    localStorage.removeItem(keyFor(projectId));
  } catch {
    /* ignore */
  }
}
