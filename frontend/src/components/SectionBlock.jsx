import Reveal from "./Reveal";
import "./SectionBlock.css";

export default function SectionBlock({ section, index }) {
  return (
    <section className="section-block" id={section.id}>
      <div className={`section-block__layout ${index % 2 === 1 ? "is-reversed" : ""}`}>
        <Reveal className="section-block__intro">
          <span className="section-kicker">{section.kicker}</span>
          <h2>{section.title}</h2>
          <p>{section.description}</p>
          <div className="section-block__bullets">
            {section.bullets.map((bullet) => (
              <div key={bullet} className="section-block__bullet">
                <span className="section-block__bullet-dot" />
                <span>{bullet}</span>
              </div>
            ))}
          </div>
        </Reveal>

        <div className={`section-block__cards section-block__cards--${section.layout}`}>
          {section.cards.map((card, cardIndex) => (
            <Reveal className="section-card" key={card.title} delay={cardIndex * 100}>
              <span className="section-card__badge">{card.badge}</span>
              <h2>{card.title}</h2>
              <p>{card.text}</p>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}
