import { z } from 'zod'

/** Mirrors the backend default MAX_MESSAGE_CHARS; the server stays the authority. */
export const MAX_MESSAGE_CHARS = 5000

export const requestFormSchema = z.object({
  message: z
    .string()
    .refine((value) => value.trim().length > 0, 'Write what you need to buy.')
    .refine(
      (value) => value.length <= MAX_MESSAGE_CHARS,
      `The message is too long (maximum ${MAX_MESSAGE_CHARS} characters).`,
    ),
})

export type RequestFormValues = z.infer<typeof requestFormSchema>
