import React from "react";
import { Link } from "react-router-dom";

export default function NotFound() {
  return (
    <div className="mx-auto max-w-md text-center py-20">
      <h1 className="text-3xl font-semibold">404</h1>
      <p className="mt-2 text-muted-foreground">
        The page you were looking for doesn’t exist.
      </p>
      <Link
        to="/dashboard"
        className="inline-flex mt-6 rounded-md bg-primary px-4 py-2 text-primary-foreground"
      >
        Go to Dashboard
      </Link>
    </div>
  );
}
