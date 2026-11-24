import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import type { RequestDetail } from '../api'
import { FIELD_STATUS_TEXT, fieldName } from '../labels'

type FieldTableProps = { fields: RequestDetail['fields'] }

/** What the AI read, after our evidence checks. Values are untrusted text. */
export function FieldTable({ fields }: FieldTableProps) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Detail</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Value</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {fields.map((field) => (
          <TableRow key={field.name}>
            <TableCell>{fieldName(field.name)}</TableCell>
            <TableCell>{FIELD_STATUS_TEXT[field.status] ?? field.status}</TableCell>
            <TableCell className="break-words whitespace-normal">{field.value ?? '—'}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
