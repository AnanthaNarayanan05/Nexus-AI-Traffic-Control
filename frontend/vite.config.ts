/// <reference types="vitest" />
/// <reference types="node" />
import { type ChildProcess, spawn } from 'node:child_process';
import net from 'node:net';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import react from '@vitejs/plugin-react';
import { defineConfig, type Plugin } from 'vite';

const here = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(here, '..');
const BACKEND_DIR = path.join(REPO_ROOT, 'backend');
const BACKEND_PYTHON = path.join(
  REPO_ROOT,
  '.venv',
  process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python',
);
const BACKEND_HOST = '127.0.0.1';
const BACKEND_PORT = 8000;

function isPortOpen(host: string, port: number, timeoutMs = 400): Promise<boolean> {
  return new Promise((resolve) => {
    const socket = net.createConnection({ host, port });
    const done = (ok: boolean) => {
      socket.destroy();
      resolve(ok);
    };
    socket.setTimeout(timeoutMs);
    socket.once('connect', () => done(true));
    socket.once('timeout', () => done(false));
    socket.once('error', () => done(false));
  });
}

/**
 * Starts the FastAPI backend (uvicorn) alongside `vite dev` so the app never opens to
 * a "backend offline" screen just because nobody remembered to start it in a second
 * terminal. Skips spawning if something is already listening on :8000 (a manually
 * started backend, or one left over from an earlier dev session) and only ever kills
 * the process it spawned itself — never an existing one.
 */
function backendAutoStart(): Plugin {
  let child: ChildProcess | null = null;
  let stopped = false;

  const stop = () => {
    if (stopped || !child) return;
    stopped = true;
    // Windows: uvicorn's reload/worker machinery can spawn a grandchild python.exe that
    // a plain kill() on the parent PID leaves running — /T also stops that subtree.
    if (process.platform === 'win32' && child.pid) {
      spawn('taskkill', ['/pid', String(child.pid), '/T', '/F']);
    } else {
      child.kill('SIGTERM');
    }
  };

  return {
    name: 'nexus-backend-autostart',
    apply: 'serve',
    async configureServer(server) {
      if (process.env.VITEST) return; // vitest never needs the live backend

      if (await isPortOpen(BACKEND_HOST, BACKEND_PORT)) {
        server.config.logger.info(
          '[backend] already answering on :8000 — leaving it running, not starting a second copy',
          { timestamp: true },
        );
        return;
      }

      server.config.logger.info('[backend] starting FastAPI on :8000 …', { timestamp: true });
      child = spawn(
        BACKEND_PYTHON,
        ['-m', 'uvicorn', 'app.main:app', '--port', String(BACKEND_PORT), '--log-level', 'warning'],
        { cwd: BACKEND_DIR, stdio: 'pipe' },
      );
      child.stdout?.on('data', (d: Buffer) => process.stdout.write(`[backend] ${d}`));
      child.stderr?.on('data', (d: Buffer) => process.stderr.write(`[backend] ${d}`));
      child.on('exit', (code) => {
        if (!stopped) {
          server.config.logger.warn(
            `[backend] process exited unexpectedly (code ${code}) — restart \`npm run dev\` to retry`,
            { timestamp: true },
          );
        }
      });

      server.httpServer?.once('close', stop);
      process.once('exit', stop);
      process.once('SIGINT', stop);
      process.once('SIGTERM', stop);
    },
  };
}

// No path alias: every import in src/ is relative, so an alias would only add a second
// resolution rule for tsc and vitest to keep in sync.
export default defineConfig({
  plugins: [react(), backendAutoStart()],
  server: {
    port: 5173,
    strictPort: false,
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./vitest.setup.ts'],
    css: false,
  },
});
