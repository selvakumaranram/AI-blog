import Link from "next/link";
import ArticleCard from "@/components/ArticleCard";
import CategoryNav from "@/components/CategoryNav";
import { getEssentialArticles } from "@/lib/articles";

export const revalidate = 900;

export default async function EssentialPage() {
  const articles = await getEssentialArticles();
  return (
    <div className="space-y-6">
      <CategoryNav />
      <h1 className="text-2xl font-bold">Essential</h1>
      {articles.length === 0 ? (
        <p className="text-sm text-gray-500">
          No essential stories yet — check the{" "}
          <Link href="/latest" className="underline">
            Latest
          </Link>{" "}
          feed.
        </p>
      ) : (
        <div className="space-y-4">
          {articles.map((article) => (
            <ArticleCard key={article.slug} article={article} />
          ))}
        </div>
      )}
    </div>
  );
}
