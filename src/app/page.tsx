import { ArrowRight, ShieldCheck } from "lucide-react";

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-8 bg-background p-8 text-foreground">
      <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-foreground/5 ring-1 ring-foreground/10">
        <ShieldCheck className="h-8 w-8" aria-hidden="true" />
      </div>

      <div className="flex max-w-md flex-col items-center gap-3 text-center">
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
          Hello, Trust Highway
        </h1>
        <p className="text-balance text-foreground/70">
          A Next.js App Router starter with TypeScript, Tailwind CSS and Lucide
          icons, ready to deploy to GitHub Pages.
        </p>
      </div>

      <a
        href="https://nextjs.org/docs"
        target="_blank"
        rel="noreferrer"
        className="inline-flex items-center gap-2 rounded-full bg-foreground px-5 py-2.5 text-sm font-medium text-background transition-opacity hover:opacity-90"
      >
        Read the docs
        <ArrowRight className="h-4 w-4" aria-hidden="true" />
      </a>
    </main>
  );
}