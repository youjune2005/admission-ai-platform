export interface ChatMessage {
  id: number;
  session_id?: number;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

export interface ChatSession {
  id: number;
  title: string;
  created_at: string;
}

export interface ChatSessionDetail extends ChatSession {
  messages: ChatMessage[];
}

export interface WorkflowTask {
  id: number;
  title: string;
  description: string | null;
  status: "todo" | "in_progress" | "done";
  due_date: string | null;
  created_at: string;
}

export interface ColumnStat {
  column: string;
  dtype: string;
  non_null_count: number;
  null_count: number;
  unique_count: number;
  numeric_summary: Record<string, number> | null;
  top_values: Record<string, number> | null;
}

export interface AnalyticsResult {
  filename: string;
  row_count: number;
  column_count: number;
  columns: ColumnStat[];
  preview: Record<string, unknown>[];
  ai_insight: string | null;
}

export interface UploadedDocument {
  id: number;
  filename: string;
  doc_type: string;
  summary: string | null;
  source: "upload" | "data_folder";
  created_at: string;
}

export interface IngestResult {
  ingested: string[];
  skipped: string[];
  failed: string[];
}
