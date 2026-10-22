import { PolicyOutcomeBadge } from '@/components/domain/PolicyOutcomeBadge'

export default function App() {
  return (
    <main className="p-8">
      <h1 className="mb-4 text-2xl font-semibold">Policy-Aware Procurement Agent</h1>
      <div className="flex gap-3">
        <PolicyOutcomeBadge outcome="CONTINUE" />
        <PolicyOutcomeBadge outcome="BLOCK" />
        <PolicyOutcomeBadge outcome="HUMAN_REVIEW" />
      </div>
    </main>
  )
}
