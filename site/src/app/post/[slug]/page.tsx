import { notFound } from "next/navigation";
import { getArticleBySlug } from "@/lib/articles";

export const revalidate = 900;

export default async function PostPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const article = await getArticleBySlug(slug);
  if (!article) {
    notFound();
  }
  return (
    <article className="space-y-4">
      <div className="text-xs text-blue-600 uppercase font-semibold">
        {article.category}
      </div>
      <h1 className="text-2xl font-bold">{article.title}</h1>
      <p className="text-slate-700">{article.summary}</p>
      <p className="text-slate-700">
        <strong>Why it matters:</strong> {article.whyItMatters}
      </p>
      <a
        href={article.sourceUrl}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-block text-blue-600 hover:underline"
      >
        Read more at {article.sourceName} →
      </a>
    </article>
  );
}
