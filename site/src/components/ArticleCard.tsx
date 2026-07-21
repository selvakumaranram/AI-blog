import Link from "next/link";
import type { Article } from "@/lib/types";

export default function ArticleCard({ article }: { article: Article }) {
  return (
    <article className="border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow">
      <div className="flex items-center gap-2 text-xs text-gray-500 mb-2">
        <span className="uppercase font-semibold">{article.category}</span>
        <span>&middot;</span>
        <span>{article.sourceName}</span>
      </div>
      <h2 className="text-lg font-semibold mb-2">
        <Link href={`/post/${article.slug}`} className="hover:underline">
          {article.title}
        </Link>
      </h2>
      <p className="text-sm text-gray-700">{article.summary}</p>
    </article>
  );
}
