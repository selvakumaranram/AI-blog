import Link from "next/link";
import { CATEGORIES } from "@/lib/types";

export default function CategoryNav() {
  return (
    <nav className="flex flex-wrap gap-3 text-sm">
      {CATEGORIES.map((category) => (
        <Link
          key={category}
          href={`/category/${category}`}
          className="px-3 py-1 rounded-full border border-gray-300 hover:bg-gray-100"
        >
          {category}
        </Link>
      ))}
    </nav>
  );
}
