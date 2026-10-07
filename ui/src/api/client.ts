import type {
  ApiKey,
  DownloadSummary,
  Feed,
  FeedItem,
  FeedItemList,
  FeedPreview,
  FeedSpec,
  FeedSummary,
  FeedUpdate,
  FolderListing,
  Health,
  IssuedApiKey,
  Job,
  JobList,
  ListDownloadsQuery,
  ListFeedItemsQuery,
  MarkAllSeenQuery,
  Preview,
  PreviewRequest,
  Principal,
  Role,
  Rule,
  RuleSpec,
  RuleUpdate,
  Submission,
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
  submitDownload(magnet: string, ruleId?: string | null): Promise<Submission>;
  cancelDownload(id: string): Promise<Job>;
  retryDownload(id: string): Promise<Job>;

  listRules(): Promise<Rule[]>;
  createRule(spec: RuleSpec): Promise<Rule>;
  /** With `spec.version`, fails with 409 rule_changed rather than overwrite a newer edit. */
  updateRule(id: string, spec: RuleUpdate): Promise<Rule>;
  deleteRule(id: string): Promise<void>;
  /** Puts every rule in this order at once. */
  reorderRules(ids: string[]): Promise<Rule[]>;
  previewRule(request: PreviewRequest): Promise<Preview>;

  listFeeds(): Promise<Feed[]>;
  createFeed(spec: FeedSpec): Promise<Feed>;
  updateFeed(id: string, changes: FeedUpdate): Promise<Feed>;
  deleteFeed(id: string): Promise<void>;
  refreshFeed(id: string): Promise<Feed>;
  /** Fetches every enabled feed now; paused ones are skipped. */
  refreshAllFeeds(): Promise<Feed[]>;
  /** The whole address, passkey included. Admins only. */
  revealFeedUrl(id: string): Promise<string>;
  previewFeed(url: string): Promise<FeedPreview>;
  listFeedItems(query: ListFeedItemsQuery): Promise<FeedItemList>;
  getFeedItem(infoHash: string): Promise<FeedItem>;
  feedSummary(): Promise<FeedSummary>;
  /** Marks exactly these items seen, e.g. the ones a list showed; returns how many. */
  markFeedItemsSeen(infoHashes: string[]): Promise<number>;
  /** Marks every unseen item in a view seen, if Charon first saw it by `upTo`. */
  markAllFeedItemsSeen(view: MarkAllSeenQuery): Promise<number>;
  downloadFeedItem(infoHash: string, ruleId?: string | null): Promise<Submission>;

  listApiKeys(): Promise<ApiKey[]>;
  issueApiKey(name: string, role: Role): Promise<IssuedApiKey>;
  revokeApiKey(id: string): Promise<ApiKey>;

  destinationRoots(): Promise<string[]>;
  destinationFolders(path: string): Promise<FolderListing>;
}
