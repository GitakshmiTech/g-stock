/**
 * Cross-platform runner for the FastAPI backend.
 * Enables running `npm run dev` or `npm start` directly inside the `backend/` folder.
 */
const { spawn, execSync } = require('child_process');
const path = require('path');

function detectPython() {
  if (process.platform === 'win32') {
    try {
      execSync('py --version', { stdio: 'ignore' });
      return 'py';
    } catch (e) {
      // Fallback to python
    }
    try {
      execSync('python --version', { stdio: 'ignore' });
      return 'python';
    } catch (e) {
      // Fallback
    }
    return 'py';
  }
  return 'python3';
}

const pythonCmd = detectPython();
const shouldReload = process.argv.includes('--reload');

console.log('='.repeat(60));
console.log('  NSE Market Data Platform - Backend Service');
console.log(`  Engine: Python / FastAPI via Uvicorn (${pythonCmd})`);
console.log('  Port:   http://localhost:8000 (Docs: http://localhost:8000/docs)');
console.log('='.repeat(60));

const uvicornArgs = [
  '-m',
  'uvicorn',
  'nse_pipeline.api.app:app',
  '--host',
  '0.0.0.0',
  '--port',
  '8000',
];

if (shouldReload) {
  uvicornArgs.push('--reload');
}

const env = {
  ...process.env,
  PYTHONPATH: [
    path.resolve(__dirname, 'src'),
    path.resolve(__dirname, '..', 'src'),
    process.env.PYTHONPATH || '',
  ].filter(Boolean).join(path.delimiter),
};

const child = spawn(pythonCmd, uvicornArgs, {
  stdio: 'inherit',
  shell: false,
  env,
  cwd: path.resolve(__dirname, '..'), // Run from project root so paths and db resolve consistently
});

child.on('error', (err) => {
  console.error('Failed to start backend process:', err.message);
  process.exit(1);
});

child.on('exit', (code, signal) => {
  process.exit(code || 0);
});
