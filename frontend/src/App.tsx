import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, NavLink, Route, Routes } from 'react-router'
import { MyRequestsPage, NewRequestPage, RequestDetailPage } from '@/features/requests'
import { ReviewQueuePage } from '@/features/reviews'
import { UserSwitcher } from '@/features/users'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <main className="mx-auto w-full max-w-3xl p-6">
          <header className="mb-6 flex flex-col gap-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-sm font-medium text-muted-foreground">
                Policy-Aware Procurement Agent
              </p>
              {import.meta.env.DEV && <UserSwitcher />}
            </div>
            <nav aria-label="Main" className="flex gap-4 text-sm">
              <NavLink to="/" end className="aria-[current=page]:font-semibold">
                My requests
              </NavLink>
              <NavLink to="/reviews" className="aria-[current=page]:font-semibold">
                Review queue
              </NavLink>
            </nav>
          </header>
          <Routes>
            <Route path="/" element={<MyRequestsPage />} />
            <Route path="/requests/new" element={<NewRequestPage />} />
            <Route path="/requests/:id" element={<RequestDetailPage />} />
            <Route path="/reviews" element={<ReviewQueuePage />} />
            <Route path="*" element={<p>Page not found.</p>} />
          </Routes>
        </main>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
