import type { components } from "./schema";

type Schemas = components["schemas"];

export type Job = Schemas["JobView"];
export type JobList = Schemas["JobListView"];
export type DownloadSummary = Schemas["DownloadSummaryView"];
export type JobStatus = Schemas["JobStatus"];
export type Rule = Schemas["Rule"];
export type RuleSpec = Schemas["RuleSpec"];
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

export interface ListDownloadsQuery {
  status?: JobStatus[];
  limit?: number;
  cursor?: string | null;
}
