import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { wireSocket } from '../store';
import { App } from './App';
import './theme.css';
import './product.css';

const host = document.getElementById('root');
if (!host) throw new Error('#root not found in index.html');

// Wire the socket before mount so the first frames land in the stores immediately.
// `wireSocket` is idempotent, which matters under StrictMode's double-invoked effects.
wireSocket();

createRoot(host).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
