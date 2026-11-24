import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Route, Routes } from 'react-router'
import { MyRequestsPage, NewRequestPage, RequestDetailPage } from '@/features/requests'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <main className="mx-auto w-full max-w-3xl p-6">
          <p className="mb-6 text-sm font-medium text-muted-foreground">
            Policy-Aware Procurement Agent
          </p>
          <Routes>
            <Route path="/" element={<MyRequestsPage />} />
            <Route path="/requests/new" element={<NewRequestPage />} />
            <Route path="/requests/:id" element={<RequestDetailPage />} />
            <Route path="*" element={<p>Page not found.</p>} />
          </Routes>
        </main>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
