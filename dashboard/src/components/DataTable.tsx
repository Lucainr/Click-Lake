import type { Column } from "../types"

interface DataTableProps<T> {
  columns: Array<Column<T>>
  rows: T[]
  rowKey: (row: T, index: number) => string
}

export const DataTable = <T extends object>({
  columns,
  rows,
  rowKey
}: DataTableProps<T>) => {
  if (!rows.length) {
    return <p className="empty">No rows</p>
  }

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={String(column.key)} className={column.align === "right" ? "align-right" : "align-left"}>
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={rowKey(row, index)}>
              {columns.map((column) => {
                const rawValue = row[column.key]
                const text =
                  column.render !== undefined
                    ? column.render(rawValue, row)
                    : String(rawValue ?? "-")

                return (
                  <td key={String(column.key)} className={column.align === "right" ? "align-right" : "align-left"}>
                    {text}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
