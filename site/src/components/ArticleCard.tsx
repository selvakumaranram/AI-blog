import Link from "next/link";
import type { Article } from "@/lib/types";

export default function ArticleCard({ article }: { article: Article }) {
  return (
    <article className="border border-blue-100 bg-white rounded-lg p-4 hover:shadow-md hover:border-blue-300 transition-all">
      <div className="flex items-center gap-2 text-xs text-blue-600 mb-2">
        <span className="uppercase font-semibold">{article.category}</span>
        <span>&middot;</span>
        <span className="text-slate-500">{article.sourceName}</span>
      </div>
      <h2 className="text-lg font-semibold mb-2">
        <Link href={`/post/${article.slug}`} className="hover:underline hover:text-blue-700">
          {article.title}
        </Link>
      </h2>
      <p className="text-sm text-slate-700">{article.summary}</p>
    </article>
  );
}
