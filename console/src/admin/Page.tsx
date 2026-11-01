import {
  Button, Dialog, DialogActions, DialogBody, DialogContent, DialogSurface, DialogTitle, DialogTrigger, Input,
  MessageBar, MessageBarActions, MessageBarBody, ToggleButton,
} from "@fluentui/react-components";
import { ArrowSortDownRegular, ArrowSortUpRegular, SearchRegular } from "@fluentui/react-icons";
import { type ReactNode, useState } from "react";
import { message } from "../api/client";

/** Title, one line about the data, and the actions, the same on every admin page. */
export function Page({ title, lead, commands, children }: {
  title: string;
  lead?: string;
  commands?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="admin-page">
      <div className="page-head">
        <div className="lead">
          <h1>{title}</h1>
          {lead && <p>{lead}</p>}
        </div>
        {commands && <div className="commands">{commands}</div>}
      </div>
      {children}
    </div>
  );
}

export function ErrorBar({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <MessageBar intent="error" role="alert">
      <MessageBarBody>{message(error)}</MessageBarBody>
    </MessageBar>
  );
}

/** Delete, after a plain question: it can't be undone. */
export function DeleteButton({ what, name, onDelete, pending }: {
  what: string;
  name: string;
  onDelete: () => void;
  pending: boolean;
}) {
  const [open, setOpen] = useState(false);
  return (
    <Dialog open={open} onOpenChange={(_, d) => setOpen(d.open)}>
      <DialogTrigger disableButtonEnhancement>
        <Button>Delete</Button>
      </DialogTrigger>
      <DialogSurface>
        <DialogBody>
          <DialogTitle>Delete {name}?</DialogTitle>
          <DialogContent>This removes the {what} for everyone. It can't be undone.</DialogContent>
          <DialogActions>
            <Button onClick={() => setOpen(false)}>Keep it</Button>
            <Button appearance="primary" disabled={pending} onClick={onDelete}>Delete {what}</Button>
          </DialogActions>
        </DialogBody>
      </DialogSurface>
    </Dialog>
  );
}

/** A saved change, with a way to put it back. */
export function UndoBar({ text, onUndo, onDismiss }: { text: string; onUndo: () => void; onDismiss: () => void }) {
  return (
    <MessageBar intent="success">
      <MessageBarBody>{text}</MessageBarBody>
      <MessageBarActions>
        <Button size="small" onClick={onUndo}>
          Undo
        </Button>
        <Button size="small" appearance="transparent" onClick={onDismiss}>
          Dismiss
        </Button>
      </MessageBarActions>
    </MessageBar>
  );
}

export interface Column<T> {
  label: string;
  /** What the column sorts by; leave out for columns that don't sort. */
  sort?: (row: T) => string | number;
  render: (row: T) => ReactNode;
}

export interface Filter<T> {
  id: string;
  label: string;
  test: (row: T) => boolean;
}

const PAGE = 50;

/** The list pattern: search, filter pills, sortable columns, 50 rows a page. */
export function DataTable<T>({ label, rows, columns, rowKey, search, filters = [], initialFilter, rowClass, rowId }: {
  label: string;
  rows: T[];
  columns: Column<T>[];
  rowKey: (row: T) => string;
  search?: (row: T) => string;
  filters?: Filter<T>[];
  initialFilter?: string | null;
  rowClass?: (row: T) => string | undefined;
  /** An id for the row, so a link can jump to it. */
  rowId?: (row: T) => string;
}) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState(initialFilter ?? null);
  const [sort, setSort] = useState<{ col: number; up: boolean } | null>(null);
  const [page, setPage] = useState(0);

  const active = filters.find((f) => f.id === filter);
  const q = query.trim().toLowerCase();
  let shown = rows.filter((r) => (!active || active.test(r)) && (!q || !search || search(r).toLowerCase().includes(q)));
  const by = sort && columns[sort.col]?.sort;
  if (sort && by) {
    shown = [...shown].sort((a, b) => {
      const x = by(a), y = by(b);
      return (x < y ? -1 : x > y ? 1 : 0) * (sort.up ? 1 : -1);
    });
  }
  const pages = Math.max(1, Math.ceil(shown.length / PAGE));
  const at = Math.min(page, pages - 1);

  return (
    <div className="list">
      {(search || filters.length > 0) && (
        <div className="list-tools">
          {search && (
            <Input
              contentBefore={<SearchRegular />}
              placeholder="Search"
              aria-label={`Search ${label}`}
              value={query}
              onChange={(_, d) => {
                setQuery(d.value);
                setPage(0);
              }}
            />
          )}
          {filters.map((f) => (
            <ToggleButton
              key={f.id}
              shape="circular"
              size="small"
              checked={filter === f.id}
              onClick={() => {
                setFilter(filter === f.id ? null : f.id);
                setPage(0);
              }}
            >
              {f.label}
            </ToggleButton>
          ))}
        </div>
      )}
      <div className="table-wrap">
        <table aria-label={label}>
          <thead>
            <tr>
              {columns.map((c, i) => (
                <th
                  key={i}
                  scope="col"
                  aria-sort={sort?.col === i ? (sort.up ? "ascending" : "descending") : undefined}
                >
                  {c.sort ? (
                    <button
                      type="button"
                      className="th-sort"
                      onClick={() => setSort({ col: i, up: sort?.col === i ? !sort.up : true })}
                    >
                      {c.label}
                      {sort?.col === i && (sort.up ? <ArrowSortUpRegular /> : <ArrowSortDownRegular />)}
                    </button>
                  ) : (
                    c.label
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.slice(at * PAGE, (at + 1) * PAGE).map((r) => (
              <tr key={rowKey(r)} id={rowId?.(r)} className={rowClass?.(r)}>
                {columns.map((c, i) => (
                  <td key={i}>{c.render(r)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {shown.length === 0 && <p className="empty">Nothing here{q || active ? " matches" : " yet"}.</p>}
      </div>
      {pages > 1 && (
        <div className="pager">
          <Button size="small" disabled={at === 0} onClick={() => setPage(at - 1)}>
            Previous
          </Button>
          <span>
            Page {at + 1} of {pages}
          </span>
          <Button size="small" disabled={at >= pages - 1} onClick={() => setPage(at + 1)}>
            Next
          </Button>
        </div>
      )}
    </div>
  );
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const two = (n: number) => String(n).padStart(2, "0");
const sameDay = (a: Date, b: Date) => a.toDateString() === b.toDateString();

/** "07:37" today, "Yesterday 21:10", "23 Oct, 14:02", and the year only when it isn't this one. */
export function when(iso: string | null, now = new Date()): string {
  if (!iso) return "";
  const d = new Date(iso);
  const time = `${two(d.getHours())}:${two(d.getMinutes())}`;
  if (sameDay(d, now)) return time;
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (sameDay(d, yesterday)) return `Yesterday ${time}`;
  const year = d.getFullYear() === now.getFullYear() ? "" : ` ${d.getFullYear()}`;
  return `${d.getDate()} ${MONTHS[d.getMonth()] ?? ""}${year}, ${time}`;
}
