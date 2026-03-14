import { useState } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { AgentSelectPage } from './pages/AgentSelectPage';
import { ChatPage } from './pages/ChatPage';
import { SetupScreen } from './components/SetupScreen';
import { getBackendUrl, clearBackendUrl } from './config';

export default function App() {
  const [connected, setConnected] = useState(() => {
    // Already configured if URL is stored in localStorage
    return !!localStorage.getItem('talon_backend_url');
  });

  const handleConnect = () => setConnected(true);

  const handleDisconnect = () => {
    clearBackendUrl();
    setConnected(false);
  };

  if (!connected) {
    return <SetupScreen onConnect={handleConnect} />;
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<AgentSelectPage onDisconnect={handleDisconnect} />} />
        <Route path="/chat/:agentId" element={<ChatPage />} />
      </Routes>
    </BrowserRouter>
  );
}
