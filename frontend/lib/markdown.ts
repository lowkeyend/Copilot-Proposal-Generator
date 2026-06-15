// Tiny, dependency-free markdown -> HTML renderer for section previews.
// Handles headings, bold, bullet/numbered lists, and simple pipe tables.
// This is for display only; export fidelity is handled server-side.

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function inline(s: string): string {
  return escapeHtml(s)
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");
}

export function renderMarkdown(md: string): string {
  const lines = md.split(/\r?\n/);
  const out: string[] = [];
  let i = 0;
  let listType: "ul" | "ol" | null = null;

  const closeList = () => {
    if (listType) {
      out.push(`</${listType}>`);
      listType = null;
    }
  };

  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();

    // table block
    if (trimmed.startsWith("|") && trimmed.includes("|")) {
      closeList();
      const rows: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith("|")) {
        rows.push(lines[i].trim());
        i++;
      }
      const parsed = rows
        .filter((r) => !/^\|?[\s:|-]+\|?$/.test(r))
        .map((r) =>
          r
            .replace(/^\|/, "")
            .replace(/\|$/, "")
            .split("|")
            .map((c) => c.trim())
        );
      if (parsed.length) {
        out.push("<table>");
        parsed.forEach((cells, idx) => {
          const tag = idx === 0 ? "th" : "td";
          out.push(
            "<tr>" + cells.map((c) => `<${tag}>${inline(c)}</${tag}>`).join("") + "</tr>"
          );
        });
        out.push("</table>");
      }
      continue;
    }

    if (!trimmed) {
      closeList();
      i++;
      continue;
    }

    if (/^#{3}\s+/.test(trimmed)) {
      closeList();
      out.push(`<h3>${inline(trimmed.replace(/^#{3}\s+/, ""))}</h3>`);
    } else if (/^#{1,2}\s+/.test(trimmed)) {
      closeList();
      out.push(`<h2>${inline(trimmed.replace(/^#{1,2}\s+/, ""))}</h2>`);
    } else if (/^[-*]\s+/.test(trimmed)) {
      if (listType !== "ul") {
        closeList();
        out.push("<ul>");
        listType = "ul";
      }
      out.push(`<li>${inline(trimmed.replace(/^[-*]\s+/, ""))}</li>`);
    } else if (/^\d+[.)]\s+/.test(trimmed)) {
      if (listType !== "ol") {
        closeList();
        out.push("<ol>");
        listType = "ol";
      }
      out.push(`<li>${inline(trimmed.replace(/^\d+[.)]\s+/, ""))}</li>`);
    } else {
      closeList();
      out.push(`<p>${inline(trimmed)}</p>`);
    }
    i++;
  }
  closeList();
  return out.join("\n");
}
