import Container from '@cloudscape-design/components/container';
import Header from '@cloudscape-design/components/header';
import ColumnLayout from '@cloudscape-design/components/column-layout';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Box from '@cloudscape-design/components/box';
import Table from '@cloudscape-design/components/table';
import StatusIndicator from '@cloudscape-design/components/status-indicator';
import ExpandableSection from '@cloudscape-design/components/expandable-section';
import KeyValuePairs from '@cloudscape-design/components/key-value-pairs';

import { Scan, Alarm, Remediation, Violation } from '../types';

interface Props {
  scans: Scan[];
  alarms: Alarm[];
  remediations: Remediation[];
  loading: boolean;
}

function AlarmStatus({ state }: { state: string }) {
  if (state === 'OK') return <StatusIndicator type="success">Healthy</StatusIndicator>;
  if (state === 'ALARM') return <StatusIndicator type="error">Alarm</StatusIndicator>;
  return <StatusIndicator type="stopped">No data</StatusIndicator>;
}

function ViolationTable({ violations, dimension }: { violations: Violation[]; dimension: string }) {
  if (dimension === 'freshness') {
    return (
      <Table
        variant="embedded"
        columnDefinitions={[
          { id: 'staleness', header: 'Staleness (hours)', cell: (v: Violation) => String(v.staleness_hours ?? v.issue ?? '-') },
          { id: 'threshold', header: 'Threshold', cell: (v: Violation) => String(v.threshold ?? '-') },
        ]}
        items={violations}
        empty="No violations"
      />
    );
  }
  if (dimension === 'distribution') {
    return (
      <Table
        variant="embedded"
        columnDefinitions={[
          { id: 'column', header: 'Column', cell: (v: Violation) => v.column || '-' },
          { id: 'outliers', header: 'Outlier Count', cell: (v: Violation) => String(v.outlier_count ?? '-') },
          { id: 'outlier_pct', header: 'Outlier %', cell: (v: Violation) => v.outlier_pct != null ? `${v.outlier_pct}%` : '-' },
          { id: 'range_found', header: 'Range Found', cell: (v: Violation) => v.min_found != null ? `${v.min_found} — ${v.max_found}` : '-' },
          { id: 'range_expected', header: 'Expected Range', cell: (v: Violation) => v.expected_min != null ? `${v.expected_min} — ${v.expected_max}` : '-' },
        ]}
        items={violations}
        empty="No violations"
      />
    );
  }
  // completeness
  return (
    <Table
      variant="embedded"
      columnDefinitions={[
        { id: 'column', header: 'Column', cell: (v: Violation) => v.column || '-' },
        { id: 'null_pct', header: 'Null %', cell: (v: Violation) => v.null_pct != null ? `${v.null_pct}%` : '-' },
        { id: 'threshold', header: 'Threshold', cell: (v: Violation) => String(v.threshold ?? '-') },
      ]}
      items={violations}
      empty="No violations"
    />
  );
}

export default function QualityDashboard({ scans, alarms, remediations, loading }: Props) {
  const latest = scans[0];
  const quarantines = remediations.filter(r => r.action_type === 'quarantine');
  const totalQuarantined = quarantines.reduce((sum, r) => sum + (r.records_affected || 0), 0);

  return (
    <SpaceBetween size="l">
      {/* Alarm Status */}
      {alarms.length > 0 && (
        <Container header={<Header variant="h2">Alarm Status</Header>}>
          <ColumnLayout columns={alarms.length} variant="text-grid">
            {alarms.map(a => (
              <div key={a.name}>
                <Box variant="awsui-key-label">{a.name.replace('DqAgent-', '')}</Box>
                <AlarmStatus state={a.state} />
              </div>
            ))}
          </ColumnLayout>
        </Container>
      )}

      {/* Latest Scan Results */}
      <Container header={<Header variant="h2">Quality Dashboard</Header>}>
        {!latest && !loading ? (
          <Box textAlign="center" color="text-body-secondary" padding="l">
            No scan results yet. Run a scan from the Control Panel.
          </Box>
        ) : latest ? (
          <SpaceBetween size="l">
            <KeyValuePairs
              columns={4}
              items={[
                { label: 'Quality Score', value: <Box variant="h1">{latest.overall_score} / 100</Box> },
                { label: 'Status', value: latest.overall_status === 'CRITICAL'
                  ? <StatusIndicator type="error">{latest.overall_status}</StatusIndicator>
                  : latest.overall_status === 'WARNING'
                  ? <StatusIndicator type="warning">{latest.overall_status}</StatusIndicator>
                  : <StatusIndicator type="success">{latest.overall_status}</StatusIndicator>
                },
                { label: 'Violations Found', value: String(latest.violation_count) },
                { label: 'Partition', value: latest.partition },
              ]}
            />

            {/* Dimension breakdown */}
            {latest.dimensions && (
              <Table
                variant="embedded"
                columnDefinitions={[
                  { id: 'dimension', header: 'Dimension', cell: ([name]) => name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) },
                  { id: 'score', header: 'Score', cell: ([, d]) => String(d.score) },
                  { id: 'status', header: 'Status', cell: ([, d]) => {
                    if (d.status === 'CRITICAL') return <StatusIndicator type="error">{d.status}</StatusIndicator>;
                    if (d.status === 'WARNING') return <StatusIndicator type="warning">{d.status}</StatusIndicator>;
                    return <StatusIndicator type="success">{d.status}</StatusIndicator>;
                  }},
                  { id: 'violations', header: 'Violations', cell: ([, d]) => String(d.violations.length) },
                ]}
                items={Object.entries(latest.dimensions)}
                empty="No dimensions"
              />
            )}

            {/* Violation details per dimension */}
            {latest.dimensions && Object.entries(latest.dimensions)
              .filter(([, d]) => d.violations.length > 0)
              .map(([name, d]) => (
                <ExpandableSection
                  key={name}
                  headerText={`${name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())} — ${d.violations.length} violation(s)`}
                >
                  <ViolationTable violations={d.violations} dimension={name} />
                </ExpandableSection>
              ))
            }
          </SpaceBetween>
        ) : null}
      </Container>

      {/* Scan History */}
      {scans.length > 1 && (
        <ExpandableSection headerText="Scan History">
          <Table
            variant="embedded"
            columnDefinitions={[
              { id: 'timestamp', header: 'Timestamp', cell: s => s.SK.slice(0, 19) },
              { id: 'partition', header: 'Partition', cell: s => s.partition },
              { id: 'score', header: 'Score', cell: s => String(s.overall_score) },
              { id: 'status', header: 'Status', cell: s => s.overall_status },
              { id: 'violations', header: 'Violations', cell: s => String(s.violation_count) },
            ]}
            items={scans}
            empty="No history"
          />
        </ExpandableSection>
      )}

      {/* Quarantine Summary */}
      {quarantines.length > 0 && (
        <Container header={<Header variant="h2">Quarantined Records</Header>}>
          <KeyValuePairs
            columns={2}
            items={[
              { label: 'Quarantine Actions', value: String(quarantines.length) },
              { label: 'Total Records Isolated', value: totalQuarantined.toLocaleString() },
            ]}
          />
        </Container>
      )}
    </SpaceBetween>
  );
}
