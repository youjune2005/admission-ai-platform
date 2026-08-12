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

export type InquiryStatus = "pending" | "generating" | "completed" | "reviewed";

export interface InquiryReference {
  document_id: number;
  filename: string;
  relevance: number;
  score: number;
  snippet: string;
  updated_at?: string | null;
}

export interface InquiryActivity {
  id: number;
  message: string;
  created_at: string;
}

export interface Inquiry {
  id: number;
  academic_year: string;
  admission_type: string;
  selection_type: string;
  asker_type: string;
  content: string;
  masked_content?: string | null;
  draft_answer?: string | null;
  ai_draft_answer?: string | null;
  status: InquiryStatus | string;
  status_label: string;
  selected_document_ids: number[];
  references: InquiryReference[];
  check_notes: string[];
  activities: InquiryActivity[];
  created_at: string;
  updated_at?: string | null;
}

export interface InquiryListResponse {
  items: Inquiry[];
  total: number;
  page: number;
  page_size: number;
}

export interface InquiryReferenceDoc {
  id: number;
  filename: string;
  category: string;
  updated_at?: string | null;
  created_at?: string | null;
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

export type RegulationStatus = "latest" | "needs_update" | "processing";

export interface UploadedDocument {
  id: number;
  filename: string;
  doc_type: string;
  summary: string | null;
  source: "upload" | "data_folder";
  category: string;
  version: string;
  status: RegulationStatus | string;
  status_label: string;
  description?: string | null;
  applied_date?: string | null;
  updated_at?: string | null;
  created_at: string;
  rag_chunk_count?: number;
}

export interface DocumentListResponse {
  items: UploadedDocument[];
  total: number;
  page: number;
  page_size: number;
  counts: {
    total: number;
    latest: number;
    needs_update: number;
    processing: number;
  };
  categories: string[];
}

export type ArchiveStatus = "draft" | "review" | "approved" | "archived";

export interface GeneratedDocument {
  id: number;
  title: string;
  source_kind: string;
  source_id: number | null;
  doc_type: string;
  admission_category: string;
  academic_year: string;
  author: string;
  last_modifier: string;
  status: ArchiveStatus;
  status_label: string;
  version: string;
  pdf_url: string | null;
  preview_url: string | null;
  approver: string | null;
  approved_at: string | null;
  archived_at: string | null;
  archive_location: string | null;
  created_at: string | null;
  updated_at: string | null;
  payload?: Record<string, unknown> | null;
}

export interface ArchiveListResponse {
  items: GeneratedDocument[];
  total: number;
  page: number;
  page_size: number;
  counts: Record<"all" | ArchiveStatus, number>;
  facets: {
    academic_years: string[];
    admission_categories: string[];
    doc_types: string[];
  };
}

export interface IngestResult {
  ingested: string[];
  skipped: string[];
  failed: string[];
}
