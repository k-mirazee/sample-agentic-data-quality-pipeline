export interface Scan {
  PK: string;
  SK: string;
  partition: string;
  overall_score: number;
  overall_status: string;
  violation_count: number;
  dimensions: Record<string, Dimension>;
}

export interface Dimension {
  score: number;
  status: string;
  violations: Violation[];
}

export interface Violation {
  // Completeness
  column?: string;
  null_pct?: number;
  threshold?: number | string;
  // Freshness
  staleness_hours?: number;
  issue?: string;
  // Distribution
  outlier_count?: number;
  outlier_pct?: number;
  min_found?: number;
  max_found?: number;
  expected_min?: number;
  expected_max?: number;
  // Common
  dimension?: string;
}

export interface Decision {
  PK: string;
  SK: string;
  decision_type: string;
  table_name?: string;
  reasoning?: string;
  action_taken?: string;
  outcome?: string;
}

export interface Alarm {
  name: string;
  state: string;
  metric: string;
  threshold?: number;
}

export interface Remediation {
  PK: string;
  SK: string;
  action_type: string;
  records_affected?: number;
  issue_id?: string;
}
