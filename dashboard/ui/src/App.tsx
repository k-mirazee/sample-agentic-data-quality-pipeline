import { useState, useEffect, useCallback } from 'react';
import AppLayout from '@cloudscape-design/components/app-layout';
import ContentLayout from '@cloudscape-design/components/content-layout';
import Header from '@cloudscape-design/components/header';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Flashbar, { FlashbarProps } from '@cloudscape-design/components/flashbar';

import ControlPanel from './components/ControlPanel';
import QualityDashboard from './components/QualityDashboard';
import AgentActivity from './components/AgentActivity';
import { fetchScans, fetchDecisions, fetchAlarms, fetchRemediations } from './api';
import { Scan, Decision, Alarm, Remediation } from './types';

export default function App() {
  const [scans, setScans] = useState<Scan[]>([]);
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [alarms, setAlarms] = useState<Alarm[]>([]);
  const [remediations, setRemediations] = useState<Remediation[]>([]);
  const [loading, setLoading] = useState(true);
  const [notifications, setNotifications] = useState<FlashbarProps.MessageDefinition[]>([]);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [s, d, a, r] = await Promise.all([
        fetchScans(),
        fetchDecisions(),
        fetchAlarms(),
        fetchRemediations(),
      ]);
      setScans(s);
      setDecisions(d);
      setAlarms(a);
      setRemediations(r);
    } catch (e) {
      setNotifications([{
        type: 'error',
        content: 'Failed to load data. Ensure the API server is running.',
        dismissible: true,
        onDismiss: () => setNotifications([]),
      }]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 10000);
    return () => clearInterval(interval);
  }, [loadData]);

  const addNotification = (msg: FlashbarProps.MessageDefinition) => {
    const id = String(Date.now());
    setNotifications(prev => [
      ...prev,
      { ...msg, id, dismissible: true, onDismiss: () => setNotifications(n => n.filter(x => x.id !== id)) },
    ]);
  };

  return (
    <AppLayout
      contentType="dashboard"
      navigationHide={true}
      toolsHide={true}
      notifications={<Flashbar items={notifications} />}
      content={
        <ContentLayout
          header={
            <Header variant="h1" description="Autonomous data quality monitoring powered by Amazon Bedrock AgentCore">
              Data Quality Agent
            </Header>
          }
        >
          <SpaceBetween size="l">
            <ControlPanel onNotification={addNotification} onRefresh={loadData} />
            <QualityDashboard scans={scans} alarms={alarms} remediations={remediations} loading={loading} />
            <AgentActivity decisions={decisions} loading={loading} />
          </SpaceBetween>
        </ContentLayout>
      }
    />
  );
}
