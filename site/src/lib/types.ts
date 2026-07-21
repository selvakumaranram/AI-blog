export type Category =
  | "video-gen"
  | "image-gen"
  | "coding"
  | "research"
  | "tools"
  | "industry";

export const CATEGORIES: Category[] = [
  "video-gen",
  "image-gen",
  "coding",
  "research",
  "tools",
  "industry",
];

export interface Article {
  id: number;
  slug: string;
  canonicalUrl: string;
  sourceUrl: string;
  sourceName: string;
  title: string;
  publishedAt: Date;
  fetchedAt: Date;
  category: Category;
  summary: string;
  whyItMatters: string;
  importance: number | null;
  sourcesCount: number;
  essential: boolean;
}
