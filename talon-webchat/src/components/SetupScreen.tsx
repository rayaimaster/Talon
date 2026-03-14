import { useState } from 'react';
import { Zap, Server, ArrowRight, Info } from 'lucide-react';
import { setBackendUrl } from '../config';

interface Props {
  onConnect: () => void;
}

export function SetupScreen({ onConnect }: Props) {
  const [url, setUrl] = useState('http://localhost:8000');
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState('');

  const handleConnect = async () => {
    setError('');
    setTesting(true);
    const clean = url.replace(/\/$/, '');
    try {
      const res = await fetch(`${clean}/api/health`, { signal: AbortSignal.timeout(5000) });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setBackendUrl(clean);
      onConnect();
    } catch (e: any) {
      setError(`Could not reach backend at ${clean}/api/health — is it running? (${e.message})`);
    } finally {
      setTesting(false);
    }
  };

  const presets = [
    { label: 'Local (default)', value: 'http://localhost:8000' },
    { label: 'Local port 3000', value: 'http://localhost:3000' },
  ];

  return (
    <div className="min-h-screen bg-gray-900 text-white flex flex-col items-center justify-center px-4">
      {/* Logo */}
      <div className="flex items-center gap-3 mb-10">
        <div className="w-12 h-12 rounded-2xl bg-blue-600 flex items-center justify-center shadow-xl">
          <Zap size={24} className="text-white" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-white leading-none">Project Talon</h1>
          <p className="text-sm text-gray-400 leading-none mt-1">Digital Employee Platform</p>
        </div>
      </div>

      {/* Card */}
      <div className="w-full max-w-md bg-gray-800/60 border border-gray-700/50 rounded-2xl p-8 shadow-2xl">
        <div className="flex items-center gap-2 mb-2">
          <Server size={18} className="text-blue-400" />
          <h2 className="text-lg font-semibold text-white">Connect to Backend</h2>
        </div>
        <p className="text-sm text-gray-400 mb-6">
          Enter the URL where your Talon backend is running.
        </p>

        {/* Presets */}
        <div className="flex gap-2 mb-3">
          {presets.map(p => (
            <button
              key={p.value}
              onClick={() => setUrl(p.value)}
              className={`text-xs px-3 py-1.5 rounded-lg border transition-colors ${
                url === p.value
                  ? 'border-blue-500 bg-blue-500/20 text-blue-300'
                  : 'border-gray-600 bg-gray-700/40 text-gray-400 hover:text-gray-200'
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>

        {/* URL input */}
        <input
          type="url"
          value={url}
          onChange={e => setUrl(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleConnect()}
          placeholder="http://localhost:8000"
          className="w-full bg-gray-900/80 border border-gray-600 rounded-xl px-4 py-3 text-white text-sm placeholder-gray-500 focus:outline-none focus:border-blue-500 transition-colors mb-4"
        />

        {/* Error */}
        {error && (
          <div className="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-xs">
            {error}
          </div>
        )}

        {/* Connect button */}
        <button
          onClick={handleConnect}
          disabled={testing || !url}
          className="w-full flex items-center justify-center gap-2 py-3 rounded-xl bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold text-sm transition-colors"
        >
          {testing ? (
            <>
              <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              Testing connection...
            </>
          ) : (
            <>
              Connect
              <ArrowRight size={16} />
            </>
          )}
        </button>

        {/* Help */}
        <div className="mt-6 p-4 rounded-xl bg-gray-900/60 border border-gray-700/40">
          <div className="flex items-center gap-1.5 text-gray-400 text-xs font-medium mb-2">
            <Info size={12} />
            How to start the backend
          </div>
          <pre className="text-xs text-gray-500 leading-relaxed whitespace-pre-wrap">{`tar -xzf talon-backend-v2.tar.gz
cd talon-backend
pip install -r requirements.txt
cp .env.example .env
# Add ANTHROPIC_API_KEY to .env
python main.py`}</pre>
          <p className="text-xs text-gray-600 mt-2">
            For public access, use{' '}
            <span className="text-gray-400 font-mono">ngrok http 8000</span>{' '}
            and enter the ngrok HTTPS URL above.
          </p>
        </div>
      </div>
    </div>
  );
}
