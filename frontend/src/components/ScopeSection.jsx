import Reveal from "./Reveal";
import "./ScopeSection.css";

function ScopeStage({ label, value }) {
  return (
    <div className="scope-stage">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export default function ScopeSection() {
  return (
    <section className="scope-section" id="scope">
      <Reveal className="scope-section__panel">
        <div className="scope-section__intro">
          <span className="section-kicker">Scope</span>
          <h3>PCB in. Parser on. Verified out.</h3>
        </div>

        <div className="scope-demo" aria-label="Animated PCB validation scope demonstration">
          <div className="scope-demo__ambient">
            <span />
            <span />
            <span />
            <span />
          </div>

          <div className="scope-demo__track">
            <div className="scope-node scope-node--input">
              <div className="scope-card scope-card--pcb">
                <span className="scope-card__tab" />
                <strong>Upload PCB</strong>
              </div>
            </div>

            <div className="scope-connector scope-connector--one">
              <span className="scope-flow-line" />
            </div>

            <div className="scope-node scope-node--vessel">
              <div className="scope-vessel">
                <div className="scope-vessel__ring" />
                <div className="scope-vessel__core">
                  <div className="scope-vessel__scan" />
                </div>
              </div>
              <small>Parsing...</small>
            </div>

            <div className="scope-connector scope-connector--two">
              <span className="scope-flow-line" />
            </div>

            <div className="scope-node scope-node--parser">
              <div className="scope-parser">
                <div className="scope-parser__header">
                  <span />
                  <span />
                  <span />
                </div>
                <div className="scope-parser__screen">
                  <div className="scope-parser__scanline" />
                  <div className="scope-parser__progress" />
                </div>
              </div>
              <small>Verifying...</small>
            </div>

            <div className="scope-connector scope-connector--three">
              <span className="scope-flow-line" />
            </div>

            <div className="scope-node scope-node--output">
              <div className="scope-result">
                <div className="scope-result__check">✓</div>
                <strong>Verified</strong>
              </div>
            </div>

            <div className="scope-file-travel" aria-hidden="true">
              <div className="scope-file-travel__card">
                <span className="scope-card__tab" />
              </div>
            </div>
          </div>
        </div>

        <div className="scope-section__stages">
          <ScopeStage label="Step 1" value="Upload PCB" />
          <ScopeStage label="Step 2" value="Parsing..." />
          <ScopeStage label="Step 3" value="Verifying..." />
          <ScopeStage label="Step 4" value="Verified" />
        </div>
      </Reveal>
    </section>
  );
}
