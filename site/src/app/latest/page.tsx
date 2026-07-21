import ArticleCard from "@/components/ArticleCard";
import CategoryNav from "@/components/CategoryNav";
import { getLatestArticles } from "@/lib/articles";

export const revalidate = 900;

export default async function LatestPage() {
  const articles = await getLatestArticles();
  return (
    <div className="space-y-6">
      <CategoryNav />
      <h1 className="text-2xl font-bold">Latest</h1>
      {articles.length === 0 ? (
        <p className="text-sm text-gray-500">No articles yet.</p>
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
