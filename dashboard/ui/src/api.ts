import { Scan, Decision, Alarm, Remediation } from './types';

const BASE = '/api';

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export const fetchScans = () => get<Scan[]>('/scans');
export const fetchDecisions = () => get<Decision[]>('/decisions');
export const fetchAlarms = () => get<Alarm[]>('/alarms');
export const fetchRemediations = () => get<Remediation[]>('/remediations');

export async function triggerScan(partition: string): Promise<{ status: string; message: string }> {
  const res = await fetch(`${BASE}/scan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ partition }),
  });
  return res.json();
}

export async function simulateEvent(partition: string): Promise<{ status: string; message: string }> {
  const res = await fetch(`${BASE}/simulate-event`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ partition }),
  });
  return res.json();
}

export async function triggerChaos(partition: string): Promise<{ status: string; message: string }> {
  const res = await fetch(`${BASE}/chaos`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ partition }),
  });
  return res.json();
}

export async function triggerRestore(clearHistory: boolean): Promise<{ status: string; message: string }> {
  const res = await fetch(`${BASE}/restore`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ clear_history: clearHistory }),
  });
  return res.json();
}
