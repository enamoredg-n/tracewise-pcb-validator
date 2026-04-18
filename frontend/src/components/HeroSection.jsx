import { heroStats } from "../data/content";
import Reveal from "./Reveal";
import "./HeroSection.css";

export default function HeroSection({ onOpenValidationCenter }) {
  return (
    <section className="hero" id="overview">
      <div className="hero__content">
        <Reveal className="hero__copy">
          <span className="section-kicker">Presentation-grade PCB validation</span>
          <h3>A modern product story for parser-led review, rule accuracy, and AI-assisted decisions.</h3>
          <p>
            TraceWise is framed like a real product launch page: confident, structured, and grounded
            in actual engineering workflow instead of generic dashboard styling.
          </p>
          <div className="hero__actions">
            <button className="button button--primary" onClick={onOpenValidationCenter}>
              Enter Validation Center
            </button>
            <a className="button button--ghost" href="#pipeline">
              Explore Workflow
            </a>
          </div>
        </Reveal>

        <Reveal className="hero__visual" delay={150}>
          <div className="hero__visual-card">
            <img src="/assets/locohoc-logo.jpeg" alt="LocoHOC logo showcase" />
          </div>
        </Reveal>
      </div>

      <div className="hero__stats">
        {heroStats.map((item, index) => (
          <Reveal className="hero__stat" key={item.label} delay={index * 100}>
            <span>{item.label}</span>
            <strong>{item.value}</strong>
          </Reveal>
        ))}
      </div>
    </section>
  );
}
