import ReactMarkdown from "react-markdown";

export default function Markdown({ content, className = "" }: { content: string; className?: string }) {
  return (
    <div className={`prose prose-sm prose-slate max-w-none ${className}`}>
      <ReactMarkdown>{content}</ReactMarkdown>
    </div>
  );
}
