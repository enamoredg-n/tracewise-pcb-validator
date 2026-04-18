import { MoonStar, SunMedium } from "lucide-react";

export default function ThemeToggle({ theme, onToggle }) {
  const isDark = theme === "dark";

  return (
    <button
      type="button"
      onClick={onToggle}
      className="group inline-flex items-center gap-3 rounded-full border border-white/15 bg-white/10 px-3 py-2 text-sm text-zinc-100 backdrop-blur transition hover:border-ember-300/50 hover:bg-white/15 dark:border-white/15 dark:bg-white/10 dark:text-zinc-100 md:px-4 light:border-zinc-300/80 light:bg-white/85 light:text-zinc-800"
      aria-label="Toggle theme"
    >
      <span className="relative flex h-6 w-11 items-center rounded-full bg-zinc-900/70 p-1 transition dark:bg-zinc-800 light:bg-orange-100">
        <span
          className={`h-4 w-4 rounded-full bg-ember-400 shadow-md transition-transform duration-300 ${
            isDark ? "translate-x-5" : "translate-x-0 bg-zinc-900"
          }`}
        />
      </span>
      <span className="hidden items-center gap-2 sm:inline-flex">
        {isDark ? <MoonStar size={16} /> : <SunMedium size={16} />}
        {isDark ? "Dark" : "Light"}
      </span>
    </button>
  );
}
