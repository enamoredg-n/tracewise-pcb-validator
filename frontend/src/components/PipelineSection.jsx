import Reveal from "./Reveal";
import "./PipelineSection.css";

export default function PipelineSection() {
  return (
    <section className="pipeline" id="pipeline">
      <Reveal className="pipeline__stage" delay={100}>
        <div className="pipeline__frame">
          <div className="pipeline__image-wrap">
            <img
              className="pipeline__image"
              src="/assets/workflow-animation.gif"
              alt="PCB validation workflow"
            />
          </div>
        </div>
      </Reveal>
    </section>
  );
}
