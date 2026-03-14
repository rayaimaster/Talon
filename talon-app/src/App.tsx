import { Routes, Route } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import Dashboard from './pages/Dashboard';
import DigitalEmployees from './pages/DigitalEmployees';
import ReActLoop from './pages/ReActLoop';
import MemoryExplorer from './pages/MemoryExplorer';
import ToolFramework from './pages/ToolFramework';
import AuditTrail from './pages/AuditTrail';
import Observability from './pages/Observability';
import ControlPlane from './pages/ControlPlane';
import Orchestration from './pages/Orchestration';
import { AppProvider } from './context/AppContext';
import { useApp } from './context/AppContext';
import SetupScreen from './components/SetupScreen';

function AppShell() {
  const { config, isConfigured, setConnection, clearConnection, error } = useApp();

  if (!isConfigured) {
    return (
      <SetupScreen
        initialApiBaseUrl={config.apiBaseUrl || 'http://localhost:8000'}
        initialAdminToken={config.adminToken}
        onSubmit={setConnection}
      />
    );
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex">
      <Sidebar />
      <main className="flex-1 ml-16 lg:ml-56 min-h-screen">
        <div className="max-w-[1600px] mx-auto p-4 lg:p-6">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-800 bg-slate-900/80 px-4 py-3 text-xs text-slate-400">
            <div>
              Connected to <span className="text-slate-200">{config.apiBaseUrl}</span>
              {error && <span className="ml-3 text-red-400">Last refresh failed: {error}</span>}
            </div>
            <button
              onClick={clearConnection}
              className="rounded-lg border border-slate-700 px-3 py-1.5 text-slate-300 transition-colors hover:border-slate-600 hover:text-white"
            >
              Change connection
            </button>
          </div>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/employees" element={<DigitalEmployees />} />
            <Route path="/react-loop" element={<ReActLoop />} />
            <Route path="/memory" element={<MemoryExplorer />} />
            <Route path="/tools" element={<ToolFramework />} />
            <Route path="/audit" element={<AuditTrail />} />
            <Route path="/observability" element={<Observability />} />
            <Route path="/control" element={<ControlPlane />} />
            <Route path="/orchestration" element={<Orchestration />} />
          </Routes>
        </div>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <AppProvider>
      <AppShell />
    </AppProvider>
  );
}
