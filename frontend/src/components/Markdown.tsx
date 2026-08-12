import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/** 마크다운 표 블록을 제거 (PDF 미리보기로 대체할 때 사용). */
export function stripMarkdownTables(content: string): string {
  const withoutFenced = content.replace(
    /```(?:markdown|md)?\s*\n([\s\S]*?)```/gi,
    (fencedBlock, body: string) =>
      /\|\s*:?-{3,}:?\s*\|/.test(body) ? "" : fencedBlock
  );
  const lines = withoutFenced.split("\n");
  const kept: string[] = [];
  let inTable = false;
  for (const line of lines) {
    const trimmed = line.trim();
    const isTableLine =
      trimmed.startsWith("|") ||
      /^\|?\s*:?-{3,}/.test(trimmed.replace(/\s/g, ""));
    if (isTableLine) {
      inTable = true;
      continue;
    }
    if (inTable && trimmed === "") {
      inTable = false;
      continue;
    }
    inTable = false;
    kept.push(line);
  }
  return kept.join("\n").replace(/\n{3,}/g, "\n\n").trim();
}

export default function Markdown({
  content,
  className = "",
  hideTables = false,
}: {
  content: string;
  className?: string;
  hideTables?: boolean;
}) {
  const source = hideTables ? stripMarkdownTables(content) : content;
  const normalizedContent = source.replace(
    /```(?:markdown|md)?\s*\n([\s\S]*?)```/gi,
    (fencedBlock, body: string) =>
      /\|\s*:?-{3,}:?\s*\|/.test(body) ? body.trim() : fencedBlock
  );

  if (!normalizedContent.trim()) {
    return null;
  }

  return (
    <div className={`prose prose-sm prose-slate min-w-0 max-w-full overflow-hidden ${className}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          table: ({ node: _node, ...props }) => (
            <div className="my-3 max-w-full overflow-x-auto overscroll-x-contain rounded-lg border border-slate-300 [-webkit-overflow-scrolling:touch]">
              <table
                {...props}
                className="m-0 w-max max-w-none border-collapse text-[11px] leading-snug"
              />
            </div>
          ),
          thead: ({ node: _node, ...props }) => (
            <thead {...props} className="bg-slate-100" />
          ),
          th: ({ node: _node, ...props }) => (
            <th
              {...props}
              className="max-w-[9rem] border-b border-r border-slate-300 px-2 py-1.5 text-center font-semibold break-words text-slate-800 last:border-r-0"
            />
          ),
          td: ({ node: _node, ...props }) => (
            <td
              {...props}
              className="max-w-[10rem] border-b border-r border-slate-200 px-2 py-1.5 align-top break-words text-slate-700 last:border-r-0"
            />
          ),
          tr: ({ node: _node, ...props }) => (
            <tr {...props} className="last:[&>td]:border-b-0" />
          ),
          pre: ({ node: _node, ...props }) => (
            <pre
              {...props}
              className="max-w-full overflow-x-auto rounded-lg bg-slate-100 p-3 text-[12px]"
            />
          ),
        }}
      >
        {normalizedContent}
      </ReactMarkdown>
    </div>
  );
}
