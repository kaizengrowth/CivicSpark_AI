// Shared Meeting Explorer types (mirrors backend schemas)

export interface AgendaItem {
  id: number;
  item_number?: string;
  title: string;
  description?: string;
  vote_result?: string;
}

export interface AgendaItemEvidence {
  id: number;
  meeting_id: number;
  item_number: string | null;
  title: string;
  description: string | null;
  section?: string | null;
  topics: string[];
  entities: {
    councilors?: string[];
    districts?: number[];
    ordinances?: string[];
    resolutions?: string[];
  };
  vote_result: string | null;
  source_page_start: number | null;
  source_page_end: number | null;
  deep_link: string;
  source_pdf_url: string | null;
}

export interface Meeting {
  id: number;
  title: string;
  description?: string;
  meeting_type: string;
  meeting_date: string;
  location?: string;
  meeting_url?: string;
  agenda_url?: string;
  minutes_url?: string;
  status: string;
  body?: string;
  external_id?: string;
  source?: string;
  document_type?: 'agenda' | 'minutes';
  topics?: string[];
  keywords?: string[];
  summary?: string;
  detailed_summary?: string;
  key_decisions?: string[];
  voting_records?: Array<{
    item_title?: string;
    agenda_item?: string;
    vote_result?: string;
    votes?: Array<{ member: string; vote: string }>;
    outcome?: string;
  }>;
  vote_statistics?: {
    total_votes: number;
    items_passed: number;
    items_failed: number;
    unanimous_votes: number;
  };
  image_paths?: string[];
}

export interface MeetingDetail {
  meeting: Meeting;
  agenda_items: AgendaItem[];
  categories: Array<{ name: string; description?: string; color?: string; icon?: string }>;
  pdf_url?: string | null;
}

export interface IngestSourceStatus {
  source_system: string;
  last_success_at: string | null;
  last_run_at: string | null;
  last_status: string | null;
  is_stale: boolean;
}

export interface IngestStatus {
  sources: IngestSourceStatus[];
  is_stale: boolean;
  stale_after_days: number;
}
