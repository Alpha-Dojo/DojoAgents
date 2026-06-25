import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import { RootErrorBoundary } from './RootErrorBoundary';
import './index.css';

const rootEl = document.getElementById('root');
if (!rootEl) {
  throw new Error('Missing #root element');
}

createRoot(rootEl).render(
  <StrictMode>
    <RootErrorBoundary>
      <App />
    </RootErrorBoundary>
  </StrictMode>,
);
