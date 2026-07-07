import { useState } from 'react';
import Container from '@cloudscape-design/components/container';
import Header from '@cloudscape-design/components/header';
import ColumnLayout from '@cloudscape-design/components/column-layout';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Button from '@cloudscape-design/components/button';
import Select, { SelectProps } from '@cloudscape-design/components/select';
import Checkbox from '@cloudscape-design/components/checkbox';
import Box from '@cloudscape-design/components/box';
import { FlashbarProps } from '@cloudscape-design/components/flashbar';

import { triggerScan, simulateEvent, triggerChaos, triggerRestore } from '../api';

const PARTITIONS: SelectProps.Option[] = [
  { value: 'year=2025/month=09', label: '2025-09' },
  { value: 'year=2025/month=08', label: '2025-08' },
  { value: 'year=2025/month=07', label: '2025-07' },
  { value: 'year=2024/month=01', label: '2024-01' },
];

interface Props {
  onNotification: (msg: FlashbarProps.MessageDefinition) => void;
  onRefresh: () => void;
}

export default function ControlPanel({ onNotification, onRefresh }: Props) {
  const [scanPartition, setScanPartition] = useState(PARTITIONS[0]);
  const [chaosPartition, setChaosPartition] = useState(PARTITIONS[0]);
  const [clearHistory, setClearHistory] = useState(true);
  const [scanLoading, setScanLoading] = useState(false);
  const [simulateLoading, setSimulateLoading] = useState(false);
  const [chaosLoading, setChaosLoading] = useState(false);
  const [restoreLoading, setRestoreLoading] = useState(false);

  const handleScan = async () => {
    setScanLoading(true);
    try {
      const res = await triggerScan(scanPartition.value!);
      onNotification({ type: res.status === 'ok' ? 'success' : 'error', content: res.message });
      onRefresh();
    } catch { onNotification({ type: 'error', content: 'Scan request failed.' }); }
    finally { setScanLoading(false); }
  };

  const handleSimulate = async () => {
    setSimulateLoading(true);
    try {
      const res = await simulateEvent(scanPartition.value!);
      onNotification({ type: res.status === 'ok' ? 'success' : 'error', content: res.message });
      onRefresh();
    } catch { onNotification({ type: 'error', content: 'Simulate event failed.' }); }
    finally { setSimulateLoading(false); }
  };

  const handleChaos = async () => {
    setChaosLoading(true);
    try {
      const res = await triggerChaos(chaosPartition.value!);
      onNotification({ type: res.status === 'ok' ? 'success' : 'error', content: res.message });
    } catch { onNotification({ type: 'error', content: 'Chaos injection failed.' }); }
    finally { setChaosLoading(false); }
  };

  const handleRestore = async () => {
    setRestoreLoading(true);
    try {
      const res = await triggerRestore(clearHistory);
      onNotification({ type: res.status === 'ok' ? 'success' : 'error', content: res.message });
      onRefresh();
    } catch { onNotification({ type: 'error', content: 'Restore failed.' }); }
    finally { setRestoreLoading(false); }
  };

  return (
    <Container header={<Header variant="h2">Control Panel</Header>}>
      <ColumnLayout columns={3} variant="text-grid">
        <SpaceBetween size="s">
          <Box variant="h3">Glue DQ Evaluation</Box>
          <Select
            selectedOption={scanPartition}
            onChange={({ detail }) => setScanPartition(detail.selectedOption)}
            options={PARTITIONS}
          />
          <SpaceBetween size="xs" direction="horizontal">
            <Button variant="primary" loading={scanLoading} onClick={handleScan}>
              Run Evaluation
            </Button>
            <Button loading={simulateLoading} onClick={handleSimulate}>
              Simulate Event
            </Button>
          </SpaceBetween>
        </SpaceBetween>

        <SpaceBetween size="s">
          <Box variant="h3">Inject Chaos</Box>
          <Select
            selectedOption={chaosPartition}
            onChange={({ detail }) => setChaosPartition(detail.selectedOption)}
            options={PARTITIONS}
          />
          <Button loading={chaosLoading} onClick={handleChaos}>
            Inject Chaos and Upload
          </Button>
        </SpaceBetween>

        <SpaceBetween size="s">
          <Box variant="h3">Restore Clean Data</Box>
          <Checkbox checked={clearHistory} onChange={({ detail }) => setClearHistory(detail.checked)}>
            Clear all scan history
          </Checkbox>
          <Button loading={restoreLoading} onClick={handleRestore}>
            Restore Everything
          </Button>
        </SpaceBetween>
      </ColumnLayout>
    </Container>
  );
}
