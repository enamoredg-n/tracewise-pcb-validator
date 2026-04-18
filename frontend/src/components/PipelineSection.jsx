import { useState } from "react";
import { pipelineSteps } from "../data/content";
import Reveal from "./Reveal";
import "./PipelineSection.css";

export default function PipelineSection() {
  const [activeIndex, setActiveIndex] = useState(0);
  const activeStep = pipelineSteps[activeIndex];

  return (
    <section className="pipeline" id="pipeline">
      <Reveal className="pipeline__intro">
        <span className="section-kicker">Pipeline</span>
        <h3>The workflow looks like a system presentation, not a static asset dropped onto a page.</h3>
        <p>
          The central image anchors the narrative while hoverable labels unpack each stage of the
          validation pipeline in plain terms.
        </p>
      </Reveal>

      <div className="pipeline__layout">
        <Reveal className="pipeline__stage" delay={100}>
          <div className="pipeline__image-wrap">
            <img
              className="pipeline__image"
              src="/assets/workflow-animation.gif"
              alt="PCB validation workflow"
            />
            <div className="pipeline__tooltip">
              <strong>{activeStep.title}</strong>
              <span>{activeStep.copy}</span>
            </div>
          </div>
        </Reveal>

        <div className="pipeline__legend">
          {pipelineSteps.map((step, index) => (
            <Reveal key={step.title} className="pipeline__legend-item" delay={index * 90}>
              <button
                className={`pipeline__chip ${activeIndex === index ? "is-active" : ""}`}
                onMouseEnter={() => setActiveIndex(index)}
                onFocus={() => setActiveIndex(index)}
                onClick={() => setActiveIndex(index)}
              >
                <span className="pipeline__chip-mark">{step.short}</span>
                <span className="pipeline__chip-copy">
                  <strong>{step.title}</strong>
                  <small>{step.copy}</small>
                </span>
              </button>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}
