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
