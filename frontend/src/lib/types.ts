export type Role = "user" | "staff" | "admin";
export type ItemType = "lost" | "found";
export type ItemStatus = "open" | "matched" | "claimed" | "returned" | "closed";

export const CATEGORIES = [
  "electronics", "wallet_bag", "keys", "id_card", "clothing", "jewelry", "documents", "pet", "other",
] as const;
export type Category = (typeof CATEGORIES)[number];

export const CATEGORY_LABEL: Record<string, string> = {
  electronics: "Electronics", wallet_bag: "Wallets & bags", keys: "Keys", id_card: "ID cards", clothing: "Clothing",
  jewelry: "Jewelry", documents: "Documents", pet: "Pets", other: "Other",
};

export interface User { id: number; name: string; email: string; role: Role; phone?: string | null }

export interface Item {
  item_id: number; item_type: ItemType; status: ItemStatus; title: string; description: string; category: Category;
  color: string | null; brand: string | null; date_lost_or_found: string; image_urls: string[]; reported_at: string;
  location_id: number; location_name: string; campus: string; suggested_matches?: number; similarity?: number;
}
export interface ItemDetail extends Item {
  reporter_name: string; is_mine: boolean; claimable: boolean; extras: Record<string, unknown>;
  my_claim?: { claim_id: number; verification_status: string; result: string; submitted_at: string } | null;
  claim_count?: number; suggested_matches: number; updated_at: string;
}
export interface Location { location_id: number; location_name: string; campus: string; building: string | null; floor: string | null }

export interface Explanation {
  rrf_score: number; boost: number; k: number; formula: string; max_possible: number; confidence: number;
  signals: { signal: "text" | "image"; similarity: number; rank: number; contribution: number }[];
}
export interface ItemMatch {
  match_id: number; status: "suggested" | "confirmed" | "rejected"; other_item_id: number; other_title: string;
  other_type: ItemType; other_status: ItemStatus; other_images: string[]; other_location: string; other_date: string;
  explanation: Explanation;
}

export interface Claim {
  claim_id: number; item_id: number; item_title: string; item_images: string[]; claimant_id: number;
  proof_description: string; proof_image_url: string | null; verification_status: string; result: string;
  submitted_at: string; reviewed_at: string | null; notes: string | null; match_id: number | null;
}
export interface QueueClaim {
  claim_id: number; item_id: number; item_title: string; item_images: string[]; claimant_name: string; claimant_email: string;
  proof_description: string; verification_status: string; submitted_at: string; competing_claims: number;
  queue_position: number; match_rrf_score: number | null; waiting_for: string;
}
export interface Notification {
  id: string; type: string; title: string; body: string; read: boolean; created_at: string; link?: string;
}
