import { Select } from '#/components/ui/Field'
import { rentaOptionLabel } from '#/lib/renta'
import type { RentaCatalogEntry } from '#/lib/api-types'
import type { SelectHTMLAttributes } from 'react'

type RentaSelectProps = Omit<
  SelectHTMLAttributes<HTMLSelectElement>,
  'value' | 'onChange' | 'children'
> & {
  value: string
  onValueChange: (value: string) => void
  entries: readonly RentaCatalogEntry[] | undefined
  /** Label of the empty option ('' value). */
  emptyLabel: string
  invalid?: boolean
}

/** Select of Renta codes labelled "código – descripción". */
export function RentaSelect({
  value,
  onValueChange,
  entries,
  emptyLabel,
  ...rest
}: RentaSelectProps) {
  const known = entries?.some((entry) => entry.code === value) ?? false
  return (
    <Select
      value={value}
      onChange={(event) => onValueChange(event.target.value)}
      {...rest}
    >
      <option value="">{emptyLabel}</option>
      {/* A saved code the catalog no longer lists (or has not loaded yet). */}
      {value && !known ? <option value={value}>{value}</option> : null}
      {entries?.map((entry) => (
        <option key={entry.code} value={entry.code}>
          {rentaOptionLabel(entry)}
        </option>
      ))}
    </Select>
  )
}
