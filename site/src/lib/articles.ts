import sql from "./db";
import type { Article, Category } from "./types";

function mapRow(row: Record<string, unknown>): Article {
  return {
    id: row.id as number,
    slug: row.slug as string,
    canonicalUrl: row.canonical_url as string,
    sourceUrl: row.source_url as string,
    sourceName: row.source_name as string,
    title: row.title as string,
    publishedAt: row.published_at as Date,
    fetchedAt: row.fetched_at as Date,
    category: row.category as Category,
    summary: row.summary as string,
    whyItMatters: row.why_it_matters as string,
    importance: row.importance as number | null,
    sourcesCount: row.sources_count as number,
    essential: row.essential as boolean,
  };
}

export async function getEssentialArticles(limit = 20): Promise<Article[]> {
  const rows = await sql`
    SELECT * FROM articles
    WHERE essential = true
    ORDER BY published_at DESC
    LIMIT ${limit}
  `;
  return rows.map(mapRow);
}

export async function getLatestArticles(limit = 50): Promise<Article[]> {
  const rows = await sql`
    SELECT * FROM articles
    ORDER BY published_at DESC
    LIMIT ${limit}
  `;
  return rows.map(mapRow);
}

export async function getArticlesByCategory(
  category: Category,
  limit = 50,
): Promise<Article[]> {
  const rows = await sql`
    SELECT * FROM articles
    WHERE category = ${category}
    ORDER BY published_at DESC
    LIMIT ${limit}
  `;
  return rows.map(mapRow);
}

export async function getArticleBySlug(slug: string): Promise<Article | null> {
  const rows = await sql`
    SELECT * FROM articles
    WHERE slug = ${slug}
    LIMIT 1
  `;
  return rows.length > 0 ? mapRow(rows[0]) : null;
}
