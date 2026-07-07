import { useState } from 'react';
import Container from '@cloudscape-design/components/container';
import Header from '@cloudscape-design/components/header';
import Table from '@cloudscape-design/components/table';
import Select, { SelectProps } from '@cloudscape-design/components/select';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Box from '@cloudscape-design/components/box';
import ColumnLayout from '@cloudscape-design/components/column-layout';
import ExpandableSection from '@cloudscape-design/components/expandable-section';
import KeyValuePairs from '@cloudscape-design/components/key-value-pairs';

import { Decision } from '../types';

interface Props {
  decisions: Decision[];
  loading: boolean;
}

export default function AgentActivity({ decisions, loading }: Props) {
  const types = [...new Set(decisions.map(d => d.decision_type))].sort();
  const typeOptions: SelectProps.Option[] = [
    { value: '__all__', label: 'All types' },
    ...types.map(t => ({ value: t, label: t })),
  ];
  const [selectedType, setSelectedType] = useState(typeOptions[0]);

  const filtered = selectedType.value === '__all__'
    ? decisions
    : decisions.filter(d => d.decision_type === selectedType.value);

  const tablesScanned = new Set(decisions.map(d => d.table_name).filter(Boolean)).size;

  return (
    <Container
      header={
        <Header
          variant="h2"
          counter={`(${decisions.length})`}
          actions={
            <Select
              selectedOption={selectedType}
              onChange={({ detail }) => setSelectedType(detail.selectedOption)}
              options={typeOptions}
            />
          }
        >
          Agent Activity
        </Header>
      }
    >
      {decisions.length === 0 && !loading ? (
        <Box textAlign="center" color="text-body-secondary" padding="l">
          No agent activity yet. Run a scan from the Control Panel.
        </Box>
      ) : (
        <SpaceBetween size="l">
          <ColumnLayout columns={3} variant="text-grid">
            <div>
              <Box variant="awsui-key-label">Total Decisions</Box>
              <Box variant="awsui-value-large">{decisions.length}</Box>
            </div>
            <div>
              <Box variant="awsui-key-label">Decision Types</Box>
              <Box variant="awsui-value-large">{types.length}</Box>
            </div>
            <div>
              <Box variant="awsui-key-label">Tables Scanned</Box>
              <Box variant="awsui-value-large">{tablesScanned}</Box>
            </div>
          </ColumnLayout>

          <Table
            variant="embedded"
            loading={loading}
            columnDefinitions={[
              { id: 'timestamp', header: 'Timestamp', cell: (d: Decision) => d.SK.slice(0, 19), width: 180 },
              { id: 'type', header: 'Type', cell: (d: Decision) => d.decision_type },
              { id: 'reasoning', header: 'Reasoning', cell: (d: Decision) => (d.reasoning || '-').slice(0, 120) },
            ]}
            items={filtered.slice(0, 30)}
            empty="No decisions match the filter."
          />

          {filtered.slice(0, 20).map((d, i) => (
            <ExpandableSection key={i} headerText={`${d.decision_type} | ${d.SK.slice(0, 19)}`}>
              <KeyValuePairs
                columns={1}
                items={[
                  { label: 'Reasoning', value: d.reasoning || 'N/A' },
                  { label: 'Action', value: d.action_taken || 'N/A' },
                  { label: 'Outcome', value: d.outcome || 'N/A' },
                ]}
              />
            </ExpandableSection>
          ))}
        </SpaceBetween>
      )}
    </Container>
  );
}
