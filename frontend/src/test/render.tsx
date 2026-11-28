import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { MyRequestsPage, NewRequestPage, RequestDetailPage } from '@/features/requests'
import { ReviewQueuePage } from '@/features/reviews'

/** Render the app's request routes at a given address, with a fresh query cache. */
export function renderAt(path: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/" element={<MyRequestsPage />} />
          <Route path="/requests/new" element={<NewRequestPage />} />
          <Route path="/requests/:id" element={<RequestDetailPage />} />
          <Route path="/reviews" element={<ReviewQueuePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}
