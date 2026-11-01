import type { ReactNode } from "react";

/** A tiny markdown subset rendered as React elements. Raw HTML stays text, because React escapes it. */

const INLINE = /\[([^\]]+)\]\(([^)\s]+)\)|\*\*(.+?)\*\*|\*(.+?)\*|_(.+?)_/g;
const SAFE_URL = /^(https?:\/\/|\/(?!\/)|#)/i;

function inline(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  for (const m of text.matchAll(INLINE)) {
    const i = m.index;
    if (i > last) out.push(text.slice(last, i));
    const [, label, href, bold, em1, em2] = m;
    if (label !== undefined && href !== undefined) {
      out.push(
        SAFE_URL.test(href) ? (
          <a key={i} href={href} rel="noopener noreferrer">
            {label}
          </a>
        ) : (
          <span key={i}>{label}</span>
        ),
      );
    } else if (bold !== undefined) out.push(<strong key={i}>{bold}</strong>);
    else out.push(<em key={i}>{em1 ?? em2}</em>);
    last = i + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

export function Markdown({ text }: { text: string }) {
  const blocks: ReactNode[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;
  const flush = () => {
    if (!list) return;
    const items = list.items.map((t, i) => <li key={i}>{inline(t)}</li>);
    blocks.push(list.ordered ? <ol key={blocks.length}>{items}</ol> : <ul key={blocks.length}>{items}</ul>);
    list = null;
  };

  for (const raw of text.split("\n")) {
    const line = raw.trim();
    const heading = /^(#{1,3})\s+(.*)$/.exec(line);
    const bullet = /^[-*]\s+(.*)$/.exec(line);
    const numbered = /^\d+[.)]\s+(.*)$/.exec(line);
    const item = bullet ?? numbered;
    if (item?.[1] !== undefined) {
      const ordered = Boolean(numbered);
      if (list && list.ordered !== ordered) flush();
      list ??= { ordered, items: [] };
      list.items.push(item[1]);
      continue;
    }
    flush();
    if (!line) continue;
    if (heading?.[1] && heading[2] !== undefined) {
      const Tag = (["h3", "h4", "h5"] as const)[heading[1].length - 1] ?? "h5";
      blocks.push(<Tag key={blocks.length}>{inline(heading[2])}</Tag>);
    } else {
      blocks.push(<p key={blocks.length}>{inline(line)}</p>);
    }
  }
  flush();
  return <div className="markdown">{blocks}</div>;
}
