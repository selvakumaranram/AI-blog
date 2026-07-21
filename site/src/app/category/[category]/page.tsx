import { notFound } from "next/navigation";
import ArticleCard from "@/components/ArticleCard";
import CategoryNav from "@/components/CategoryNav";
import { getArticlesByCategory } from "@/lib/articles";
import { CATEGORIES, type Category } from "@/lib/types";

export const revalidate = 900;

function isCategory(value: string): value is Category {
  return (CATEGORIES as string[]).includes(value);
}

export default async function CategoryPage({
  params,
}: {
  params: Promise<{ category: string }>;
}) {
  const { category } = await params;
  if (!isCategory(category)) {
    notFound();
  }
  const articles = await getArticlesByCategory(category);
  return (
    <div className="space-y-6">
      <CategoryNav />
      <h1 className="text-2xl font-bold">{category}</h1>
      <div className="space-y-4">
        {articles.map((article) => (
          <ArticleCard key={article.slug} article={article} />
        ))}
      </div>
    </div>
  );
}
