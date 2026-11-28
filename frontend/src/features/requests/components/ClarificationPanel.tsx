import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import type { ClarificationRound, RequestDetail } from '../api'
import { useAnswerClarification } from '../hooks'
import { formatDate } from '../labels'
import { MAX_ANSWER_CHARS, answerFormSchema, type AnswerFormValues } from '../schemas'

type ClarificationPanelProps = { request: RequestDetail }

/**
 * Follow-up questions and the employee's answers (D-064). Questions are fixed system text;
 * answers are the employee's own words and are shown as plain text only.
 */
export function ClarificationPanel({ request }: ClarificationPanelProps) {
  const rounds = request.clarifications
  const last = rounds[rounds.length - 1]
  const open = request.status === 'NEEDS_CLARIFICATION' && last && last.answer === null
  return (
    <section aria-labelledby="clarification-heading" className="flex flex-col gap-3">
      <h2 id="clarification-heading" className="text-lg font-semibold">
        Follow-up questions
      </h2>
      {rounds.map((round) => (
        <RoundView
          key={round.round_number}
          round={round}
          total={request.max_clarification_rounds}
        />
      ))}
      {open && (
        <AnswerForm
          requestId={request.id}
          isLastRound={last.round_number >= request.max_clarification_rounds}
        />
      )}
    </section>
  )
}

function RoundView({ round, total }: { round: ClarificationRound; total: number }) {
  return (
    <div className="flex flex-col gap-2 rounded-lg border p-3">
      <p className="text-sm text-muted-foreground">
        Round {round.round_number} of {total} · asked {formatDate(round.asked_at)}
      </p>
      <ul className="list-disc pl-5">
        {round.questions.map((q) => (
          <li key={q.field}>{q.question}</li>
        ))}
      </ul>
      {round.answer !== null && (
        <div className="flex flex-col gap-1">
          <p className="text-sm font-medium">Your answer</p>
          <p className="break-words whitespace-pre-wrap">{round.answer}</p>
        </div>
      )}
    </div>
  )
}

function AnswerForm({ requestId, isLastRound }: { requestId: string; isLastRound: boolean }) {
  const answer = useAnswerClarification(requestId)
  const form = useForm<AnswerFormValues>({
    resolver: zodResolver(answerFormSchema),
    defaultValues: { answer: '' },
  })
  const fieldError = form.formState.errors.answer?.message

  const onSubmit = form.handleSubmit((values) => {
    answer.mutate(values.answer, {
      onSuccess: () => form.reset(),
      onError: (error) => {
        const serverField = error.fieldErrors?.answer
        if (serverField) form.setError('answer', { message: serverField })
      },
    })
  })

  const generalError = answer.error && !answer.error.fieldErrors?.answer ? answer.error : null

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-3">
      <Label htmlFor="answer">Your answer</Label>
      <Textarea
        id="answer"
        rows={3}
        maxLength={MAX_ANSWER_CHARS}
        placeholder="For example: The total is about Rs 30,000."
        aria-invalid={fieldError ? true : undefined}
        aria-describedby={fieldError ? 'answer-error' : 'answer-hint'}
        {...form.register('answer')}
      />
      <p id="answer-hint" className="text-xs text-muted-foreground">
        {isLastRound
          ? 'This is the last round. If details are still missing, a person will review the request.'
          : 'Your request will be checked again with your answer.'}
      </p>
      {fieldError && (
        <p id="answer-error" className="text-sm text-destructive">
          {fieldError}
        </p>
      )}
      {generalError && (
        <p role="alert" className="text-sm text-destructive">
          {generalError.message}
        </p>
      )}
      <div>
        <Button type="submit" disabled={answer.isPending}>
          {answer.isPending ? 'Sending…' : 'Send answer'}
        </Button>
      </div>
    </form>
  )
}
