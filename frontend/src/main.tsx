/**
 * main.tsx — application entry point.
 *
 * Sets up React Query's query client (manages all server-state caching)
 * before mounting the app tree.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import './index.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Retry failed queries once (network blip tolerance)
      retry: 1,
      // Keep cached data fresh for 2 minutes by default;
      // individual queries can override with their own staleTime
      staleTime: 2 * 60 * 1000,
      // Always attempt the actual fetch instead of trusting the browser's
      // navigator.onLine / online-offline events. TanStack Query's default
      // 'online' mode pauses every query indefinitely (fetchStatus: 'paused',
      // never loading, never erroring, data stays undefined forever) if the
      // browser's online-status detection is ever wrong — a known mobile
      // browser quirk (backgrounding/foregrounding, brief signal drops) that
      // silently strands the user with no error and no way to recover short
      // of a full app restart. Real connectivity failures still surface
      // normally through the fetch itself failing.
      networkMode: 'always',
    },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
)
