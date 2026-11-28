import { useQuery, useQueryClient } from '@tanstack/react-query'
import { setDemoUser } from '@/lib/api-client'
import { getDemoUsers, getMe } from './api'

/**
 * Development only (D-065): pick which demo user the app acts as, to try the review
 * workflow without login. Not security; the backend refuses it outside development.
 */
export function UserSwitcher() {
  const queryClient = useQueryClient()
  const me = useQuery({ queryKey: ['me'], queryFn: getMe })
  const users = useQuery({ queryKey: ['demo-users'], queryFn: getDemoUsers })
  if (!me.isSuccess || !users.isSuccess) return null

  const onChange = (email: string) => {
    setDemoUser(email)
    // Everything cached belongs to the previous user.
    queryClient.clear()
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
