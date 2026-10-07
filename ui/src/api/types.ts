import type { components } from "./schema";

type Schemas = components["schemas"];

export type Job = Schemas["JobView"];
export type JobList = Schemas["JobListView"];
export type DownloadSummary = Schemas["DownloadSummaryView"];
export type JobStatus = Schemas["JobStatus"];
export type JobError = Schemas["JobErrorView"];
export type Actor = Schemas["Actor"];
export type Rule = Schemas["Rule"];
export type RuleSpec = Schemas["RuleSpec"];
export type RuleUpdate = Schemas["RuleUpdate"];
export type RenameStep = Schemas["RenameStep"];
export type MatchType = Schemas["MatchType"];
export type Preview = Schemas["PreviewView"];
export type PreviewRequest = Schemas["PreviewRequest"];
export type ApiKey = Schemas["ApiKeyView"];
export type IssuedApiKey = Schemas["IssuedApiKeyView"];
export type Role = Schemas["Role"];
export type Principal = Schemas["PrincipalView"];
export type Health = Schemas["HealthView"];
export type FolderListing = Schemas["FolderListingView"];
export type ErrorDetail = Schemas["ErrorDetail"];
export type Feed = Schemas["FeedView"];
export type FeedSpec = Schemas["FeedSpec"];
export type FeedUpdate = Schemas["FeedUpdate"];
export type FeedItem = Schemas["FeedItemView"];
export type ItemJob = Schemas["ItemJobView"];
export type FeedItemList = Schemas["FeedItemListView"];
export type FeedPreview = Schemas["FeedPreviewView"];
export type FeedSummary = Schemas["FeedSummaryView"];
export type MatchFilter = Schemas["MatchFilter"];
export type Problem = Schemas["ProblemView"];

export interface ListDownloadsQuery {
  status?: JobStatus[];
  limit?: number;
  cursor?: string | null;
}

/** A download request's outcome: `created` is false when the torrent was already in Charon. */
export interface Submission {
  job: Job;
  created: boolean;
}

/** A view of the inbox to mark seen, up to the newest first-seen time it showed. */
export interface MarkAllSeenQuery {
  upTo: string;
  feedId?: string | null;
  match?: MatchFilter;
  q?: string;
}

export interface ListFeedItemsQuery {
  feedId?: string | null;
  match?: MatchFilter;
  unseen?: boolean;
  q?: string | null;
  limit?: number;
  cursor?: string | null;
}
