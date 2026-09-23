export interface ThreadEvidence {
  sourceKind?: "threads" | "press";
  url: string;
  title: string;
  summary: string;
  stance: "complaint" | "support" | "mixed" | "unclear";
  scope: "street" | "city" | "unclear";
  publishedAt: null;
}
export interface ThreadsEvidence {
  question: string;
  queries: string[];
  searchedQueries: string[];
  location: string;
  posts: ThreadEvidence[];
  fetchedAt: string;
  cached: boolean;
  provider: "OpenAI web search";
  coverage: string;
}
