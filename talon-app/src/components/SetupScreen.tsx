import { useState } from 'react';
import { Shield, Server, KeyRound } from 'lucide-react';

interface SetupScreenProps {
  initialApiBaseUrl: string;
  initialAdminToken: string;
  onSubmit: (apiBaseUrl: string, adminToken: string) => void;
}

export default function SetupScreen({
  initialApiBaseUrl,
  initialAdminToken,
  onSubmit,
}: SetupScreenProps) {
  const [apiBaseUrl, setApiBaseUrl] = useState(initialApiBaseUrl);
  const [adminToken, setAdminToken] = useState(initialAdminToken);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex items-center justify-center p-6">
      <div className="w-full max-w-xl rounded-3xl border border-slate-800 bg-slate-900/80 p-8 shadow-2xl shadow-slate-950/60">
        <div className="mb-8">
          <div className="mb-4 inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-500/15 text-blue-400">
            <Shield className="h-6 w-6" />
          </div>
          <h1 className="text-3xl font-bold text-white">Project Talon Admin Console</h1>
          <p className="mt-2 text-sm text-slate-400">
            Connect this dashboard to your local backend with an admin token so the controls
            reflect real agent state instead of demo data.
          </p>
        </div>

        <form
          className="space-y-5"
          onSubmit={(event) => {
            event.preventDefault();
            onSubmit(apiBaseUrl, adminToken);
          }}
        >
          <label className="block">
            <span className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-300">
              <Server className="h-4 w-4 text-blue-400" />
              Backend API URL
            </span>
            <input
              type="url"
              value={apiBaseUrl}
              onChange={(event) => setApiBaseUrl(event.target.value)}
              placeholder="http://localhost:8000"
              className="w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm text-slate-100 outline-none transition-colors focus:border-blue-500"
              required
            />
          </label>

          <label className="block">
            <span className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-300">
              <KeyRound className="h-4 w-4 text-blue-400" />
              X-Admin-Token
            </span>
            <input
              type="password"
              value={adminToken}
              onChange={(event) => setAdminToken(event.target.value)}
              placeholder="Enter the backend admin token"
              className="w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm text-slate-100 outline-none transition-colors focus:border-blue-500"
              required
            />
          </label>

          <button
            type="submit"
            className="w-full rounded-xl bg-blue-600 px-4 py-3 text-sm font-semibold text-white transition-colors hover:bg-blue-500"
          >
            Connect Admin Console
          </button>
        </form>

        <div className="mt-6 rounded-2xl border border-slate-800 bg-slate-950/80 p-4 text-xs text-slate-400">
          Expected local setup: backend on `http://localhost:8000`, plus the same
          `ADMIN_API_TOKEN` value you configured for FastAPI.
        </div>
      </div>
    </div>
  );
}
