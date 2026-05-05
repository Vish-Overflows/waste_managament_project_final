export type Role = "staff" | "operator" | "admin";

export interface User {
  id: number;
  username: string;
  role: Role;
  active: boolean;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface CollectionRecord {
  id: number;
  employee_id: string;
  housing_block: string;
  room_number: string;
  collection_date: string;
  status: string;
  processed_at: string | null;
  created_at: string;
}

export interface PaginatedCollections {
  items: CollectionRecord[];
  total: number;
  page: number;
  page_size: number;
}

export interface WasteEntry {
  id: number;
  employee_id: string;
  waste_category: string;
  waste_subtype: string;
  housing_block: string;
  room_number: string;
  quantity: number;
  collection_id: number | null;
  created_at: string;
}

export interface ProcessingTotals {
  entries_count: number;
  total_weight: number;
  dry_weight: number;
  wet_weight: number;
}

export interface PaginatedWasteEntries {
  items: WasteEntry[];
  total: number;
  page: number;
  page_size: number;
}

export interface WetProcessingRecord {
  employee_id: string;
  compost_quantity: number;
  biogas_quantity: number;
  total_wet_reference: number;
  created_at: string;
  notes?: string | null;
}

export interface CompostDistributionRecord {
  employee_id: string;
  recipient: string;
  quantity: number;
  distribution_date: string;
  created_at: string;
}

export interface WetProcessingStatus {
  total_wet_processed: number;
  compost_deposited: number;
  biogas_deposited: number;
  compost_distributed: number;
  latest_update: WetProcessingRecord | null;
  latest_distributions: CompostDistributionRecord[];
}

export interface SummaryMetric {
  label: string;
  value: string | number;
}

export interface TrendPoint {
  date: string;
  total_weight: number;
}

export interface CategoryBreakdownPoint {
  label: string;
  dry_weight: number;
  wet_weight: number;
}

export interface BlockStat {
  housing_block: string;
  collections_count: number;
  processed_weight: number;
}

export interface OperatorStat {
  employee_id: string;
  entries_count: number;
  total_weight: number;
}
