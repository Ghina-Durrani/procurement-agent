import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { useSubmitRequest } from '../hooks'
import { MAX_MESSAGE_CHARS, requestFormSchema, type RequestFormValues } from '../schemas'

type RequestFormProps = { onSubmitted: (id: string) => void }

/** The employee writes the request in their own words; the server checks and decides. */
export function RequestForm({ onSubmitted }: RequestFormProps) {
  const submit = useSubmitRequest()
  const form = useForm<RequestFormValues>({
    resolver: zodResolver(requestFormSchema),
    defaultValues: { message: '' },
  })
  const fieldError = form.formState.errors.message?.message

  const onSubmit = form.handleSubmit((values) => {
    submit.mutate(values.message, {
      onSuccess: (created) => onSubmitted(created.id),
      onError: (error) => {
        const serverField = error.fieldErrors?.message
        if (serverField) form.setError('message', { message: serverField })
      },
    })
  })

  const generalError = submit.error && !submit.error.fieldErrors?.message ? submit.error : null

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-3">
      <Label htmlFor="message">What do you need to buy?</Label>
      <Textarea
        id="message"
        rows={6}
        maxLength={MAX_MESSAGE_CHARS}
        placeholder="For example: Need 3 office chairs from Metro Furniture, about Rs 30,000, for the new meeting room."
        aria-invalid={fieldError ? true : undefined}
        aria-describedby={fieldError ? 'message-error' : undefined}
        {...form.register('message')}
      />
      {fieldError && (
        <p id="message-error" className="text-sm text-destructive">
          {fieldError}
        </p>
      )}
      {generalError && (
        <p role="alert" className="text-sm text-destructive">
          {generalError.message}
        </p>
      )}
      <div>
        <Button type="submit" disabled={submit.isPending}>
          {submit.isPending ? 'Submitting…' : 'Submit request'}
        </Button>
      </div>
    </form>
  )
}
