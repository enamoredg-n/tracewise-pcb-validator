import { useEffect, useMemo, useState } from "react";
import Footer from "./components/Footer";
import HeroSection from "./components/HeroSection";
import Navbar from "./components/Navbar";
import PipelineSection from "./components/PipelineSection";
import ScrollToTopButton from "./components/ScrollToTopButton";
import ScopeSection from "./components/ScopeSection";
import SectionBlock from "./components/SectionBlock";
import ValidationCenter from "./components/ValidationCenter";
import { featureSections, navLinks } from "./data/content";
import "./App.css";

function useTheme() {
  const [theme, setTheme] = useState(() => localStorage.getItem("tracewise-theme") || "dark");

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("tracewise-theme", theme);
  }, [theme]);

  return [theme, () => setTheme((current) => (current === "dark" ? "light" : "dark"))];
}

export default function App() {
  const [theme, toggleTheme] = useTheme();
  const [activeView, setActiveView] = useState("home");

  const visibleLinks = useMemo(
    () => navLinks.map((item) => ({ ...item, disabled: activeView !== "home" })),
    [activeView],
  );

  const openValidationCenter = () => {
    setActiveView("validation");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const openHome = () => {
    setActiveView("home");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  return (
    <div className="app-shell">
      <div className="app-background" aria-hidden="true" />
      <Navbar
        theme={theme}
        navLinks={visibleLinks}
        onNavigateHome={openHome}
        onOpenValidationCenter={openValidationCenter}
        onToggleTheme={toggleTheme}
      />

      {activeView === "home" ? (
        <main>
          <HeroSection onOpenValidationCenter={openValidationCenter} />
          <PipelineSection />
          {featureSections.map((section, index) => (
            section.id === "scope" ? (
              <ScopeSection key={section.id} />
            ) : (
              <SectionBlock key={section.id} section={section} index={index} />
            )
          ))}
          <section className="cta-panel reveal">
            <div className="cta-panel__copy">
              <span className="section-kicker">Product Flow</span>
              <h2>Move from presentation to action without losing the story.</h2>
              <p>
                The landing page introduces the system with confidence. The Validation Center takes
                the same ideas into an operational workflow for real board review.
              </p>
            </div>
            <button className="button button--primary" onClick={openValidationCenter}>
              Open Validation Center
            </button>
          </section>
          <Footer />
        </main>
      ) : (
        <ValidationCenter />
      )}

      <ScrollToTopButton />
    </div>
  );
}
