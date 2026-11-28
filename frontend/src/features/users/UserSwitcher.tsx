import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { type ApiError, getDemoUser, setDemoUser } from '@/lib/api-client'
import { getDemoUsers, getMe } from './api'

/**
 * Development only (D-065): pick which demo user the app acts as, to try the review
 * workflow without login. Not security; the backend refuses it outside development.
 */
export function UserSwitcher() {
  const queryClient = useQueryClient()
  const me = useQuery({ queryKey: ['me'], queryFn: getMe })
  const users = useQuery({ queryKey: ['demo-users'], queryFn: getDemoUsers })

  // A saved user that no longer exists (for example after the database was reset) would
  // lock every page out. Forget it and go back to the default demo user.
  const savedUserRefused =
    (me.error as ApiError | null)?.code === 'UNAUTHENTICATED' && getDemoUser() !== null
  useEffect(() => {
    if (savedUserRefused) {
      setDemoUser(null)
      void queryClient.resetQueries()
    }
  }, [savedUserRefused, queryClient])

  if (!me.isSuccess || !users.isSuccess) return null

  const onChange = (email: string) => {
    setDemoUser(email)
    // Every cached answer belongs to the previous user: reset the cache AND fetch again
    // everything on screen (clear() alone removed the data without fetching it again).
    void queryClient.resetQueries()
  }

  return (
    <label className="flex items-center gap-2 text-sm">
      <span className="text-muted-foreground">Acting as (dev only)</span>
      <select
        aria-label="Acting as"
        className="rounded-md border bg-background px-2 py-1"
        value={me.data.email}
        onChange={(event) => onChange(event.target.value)}
      >
        {users.data.users.map((user) => (
          <option key={user.email} value={user.email}>
            {user.full_name} ({user.role})
          </option>
        ))}
      </select>
    </label>
  )
}
