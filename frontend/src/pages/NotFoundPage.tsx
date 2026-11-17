import { Link } from "react-router-dom";
import { BrandMark } from "../components/Brand";

export function NotFoundPage() {
  return (
    <div className="flex h-full flex-col items-center justify-center px-6 text-center">
      <BrandMark className="h-12 w-12" />
      <p className="mt-6 text-[11px] font-semibold uppercase tracking-widest muted">404</p>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight">Page not found</h1>
      <p className="mt-2 text-sm muted">The page you're looking for doesn't exist.</p>
      <Link to="/" className="btn-primary mt-6">
        Back to chat
      </Link>
    </div>
  );
}