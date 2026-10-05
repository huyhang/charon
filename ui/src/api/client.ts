import type {
  ApiKey,
  DownloadSummary,
  FolderListing,
  Health,
  IssuedApiKey,
  Job,
  JobList,
  ListDownloadsQuery,
  Preview,
  PreviewRequest,
  Principal,
  Role,
  Rule,
  RuleSpec,
} from "./types";

/**
 * Everything the UI can ask of Charon. Components depend on this interface only;
 * the HTTP implementation is injected at the root, and tests inject a fake.
 * Methods reject with ApiError when Charon answers with an error.
 */
export interface CharonClient {
  me(): Promise<Principal>;
  health(): Promise<Health>;

  listDownloads(query: ListDownloadsQuery): Promise<JobList>;
  downloadSummary(): Promise<DownloadSummary>;
  getDownload(id: string): Promise<Job>;
  submitDownload(magnet: string, ruleId?: string | null): Promise<Job>;
  cancelDownload(id: string): Promise<Job>;
  retryDownload(id: string): Promise<Job>;

  listRules(): Promise<Rule[]>;
  createRule(spec: RuleSpec): Promise<Rule>;
  updateRule(id: string, spec: RuleSpec): Promise<Rule>;
  deleteRule(id: string): Promise<void>;
  previewRule(request: PreviewRequest): Promise<Preview>;

  listApiKeys(): Promise<ApiKey[]>;
  issueApiKey(name: string, role: Role): Promise<IssuedApiKey>;
  revokeApiKey(id: string): Promise<ApiKey>;

  destinationRoots(): Promise<string[]>;
  destinationFolders(path: string): Promise<FolderListing>;
}
