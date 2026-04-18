import { useEffect, useMemo, useState } from "react";
import { fetchBootstrap, runValidationRequest } from "../api";
import Reveal from "./Reveal";
import "./ValidationCenter.css";

function RuleField({ label, name, value, onChange, step = "0.1", type = "number" }) {
  return (
    <label className="validation-form__field">
      <span>{label}</span>
      <input
        name={name}
        type={type}
        step={step}
        value={type === "checkbox" ? undefined : value}
        checked={type === "checkbox" ? Boolean(value) : undefined}
        onChange={onChange}
      />
    </label>
  );
}

function ResultTable({ rows }) {
  if (!rows?.length) {
    return null;
  }

  return (
    <div className="validation-results__table-wrap">
      <table className="validation-results__table">
        <thead>
          <tr>
            <th>Source</th>
            <th>Rule</th>
            <th>Status</th>
            <th>Severity</th>
            <th>Message</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={`${row.Rule}-${index}`}>
              <td>{row.Source}</td>
              <td>{row.Rule}</td>
              <td>
                <span className={`status-pill status-pill--${String(row.Status).toLowerCase()}`}>
                  {row.Status}
                </span>
              </td>
              <td>{row.Severity}</td>
              <td>{row.Message}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function ValidationCenter() {
  const [bootstrap, setBootstrap] = useState(null);
  const [bootstrapError, setBootstrapError] = useState("");
  const [candidateFile, setCandidateFile] = useState(null);
  const [referenceFile, setReferenceFile] = useState(null);
  const [useBundledReference, setUseBundledReference] = useState(false);
  const [rules, setRules] = useState({});
  const [tolerances, setTolerances] = useState({});
  const [result, setResult] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [preset, setPreset] = useState("custom");

  useEffect(() => {
    let mounted = true;

    fetchBootstrap()
      .then((payload) => {
        if (!mounted) return;
        setBootstrap(payload);
        setRules(payload.custom_rules);
        setTolerances(payload.default_tolerances);
        setUseBundledReference(Boolean(payload.bundled_reference_available));
      })
      .catch((error) => {
        if (!mounted) return;
        setBootstrapError(error.message);
      });

    return () => {
      mounted = false;
    };
  }, []);

  const summaryCards = useMemo(() => {
    if (!result) return [];
    return [
      { label: "Validation Score", value: `${result.summary.validation_score}/100` },
      { label: "Critical", value: result.severity_counts.Critical || 0 },
      { label: "Major", value: result.severity_counts.Major || 0 },
      { label: "Minor", value: result.severity_counts.Minor || 0 },
    ];
  }, [result]);

  const applyPreset = (nextPreset) => {
    if (!bootstrap) return;
    setPreset(nextPreset);
    if (nextPreset === "triac") {
      setRules(bootstrap.triac_sample_rules);
      setUseBundledReference(Boolean(bootstrap.bundled_reference_available));
    } else {
      setRules(bootstrap.custom_rules);
    }
  };

  const handleRuleChange = (event) => {
    const { name, value, type, checked } = event.target;
    setRules((current) => ({
      ...current,
      [name]: type === "checkbox" ? checked : Number(value),
    }));
  };

  const handleToleranceChange = (event) => {
    const { name, value } = event.target;
    setTolerances((current) => ({
      ...current,
      [name]: Number(value),
    }));
  };

  const downloadReport = () => {
    if (!result?.report?.pdf_base64) return;
    const link = document.createElement("a");
    link.href = `data:application/pdf;base64,${result.report.pdf_base64}`;
    link.download = result.report.filename || "validation-report.pdf";
    link.click();
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!candidateFile) {
      setSubmitError("Choose a candidate .kicad_pcb or .dxf file first.");
      return;
    }

    setSubmitting(true);
    setSubmitError("");

    try {
      const payload = await runValidationRequest({
        candidateFile,
        referenceFile,
        rules,
        tolerances,
        useBundledReference: useBundledReference && !referenceFile,
      });
      setResult(payload);
    } catch (error) {
      setSubmitError(error.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="validation-center">
      <section className="validation-center__hero">
        <Reveal className="validation-center__copy">
          <span className="section-kicker">Validation Center</span>
          <h3>Welcome to the Validation Center</h3>
          <p>
            Upload a candidate board, adjust exact rule thresholds, compare against a reference,
            and download the report directly from this interface.
          </p>
          {bootstrapError ? <div className="validation-banner validation-banner--error">{bootstrapError}</div> : null}
        </Reveal>

        <Reveal className="validation-center__visual" delay={140}>
          {result?.candidate?.preview_png_base64 ? (
            <img
              src={`data:image/png;base64,${result.candidate.preview_png_base64}`}
              alt="Candidate PCB preview"
            />
          ) : (
            <div className="validation-center__placeholder">
              <strong>Board preview will appear here</strong>
              <span>Run a validation to render the generated PCB preview and issue summary.</span>
            </div>
          )}
        </Reveal>
      </section>

      <section className="validation-workspace">
        <form className="validation-form" onSubmit={handleSubmit}>
          <div className="validation-form__section">
            <div className="validation-form__header">
              <h3>Input</h3>
              <p>Bring in the candidate board and decide whether to compare against a reference.</p>
            </div>

            <label className="validation-form__upload">
              <span>Candidate board</span>
              <input
                type="file"
                accept=".kicad_pcb,.dxf"
                onChange={(event) => setCandidateFile(event.target.files?.[0] || null)}
              />
            </label>

            <label className="validation-form__upload">
              <span>Optional reference board</span>
              <input
                type="file"
                accept=".kicad_pcb,.dxf"
                onChange={(event) => setReferenceFile(event.target.files?.[0] || null)}
              />
            </label>

            <label className="validation-form__toggle">
              <input
                type="checkbox"
                checked={useBundledReference}
                onChange={(event) => setUseBundledReference(event.target.checked)}
                disabled={!bootstrap?.bundled_reference_available || Boolean(referenceFile)}
              />
              <span>
                Use bundled TRIAC reference
                <small>
                  {bootstrap?.bundled_reference_name
                    ? `Available: ${bootstrap.bundled_reference_name}`
                    : "No bundled reference found"}
                </small>
              </span>
            </label>
          </div>

          <div className="validation-form__section">
            <div className="validation-form__header">
              <h3>Rules</h3>
              <p>Switch between a custom rule set and the TRIAC sample limits derived from the demo board.</p>
            </div>

            <div className="validation-form__preset-row">
              <button
                type="button"
                className={`button ${preset === "custom" ? "button--primary" : "button--ghost"}`}
                onClick={() => applyPreset("custom")}
              >
                Custom
              </button>
              <button
                type="button"
                className={`button ${preset === "triac" ? "button--primary" : "button--ghost"}`}
                onClick={() => applyPreset("triac")}
              >
                TRIAC Sample
              </button>
            </div>

            <div className="validation-form__grid">
              <RuleField label="Total drills" name="expected_drill_count" value={rules.expected_drill_count ?? 0} onChange={handleRuleChange} step="1" />
              <RuleField label="Plated drills" name="expected_plated_drill_count" value={rules.expected_plated_drill_count ?? 0} onChange={handleRuleChange} step="1" />
              <RuleField label="Mounting holes" name="expected_mounting_hole_count" value={rules.expected_mounting_hole_count ?? 0} onChange={handleRuleChange} step="1" />
              <RuleField label="Min hole diameter (mm)" name="min_hole_diameter" value={rules.min_hole_diameter ?? 0} onChange={handleRuleChange} />
              <RuleField label="Max hole diameter (mm)" name="max_hole_diameter" value={rules.max_hole_diameter ?? 0} onChange={handleRuleChange} />
              <RuleField label="Min trace width (mm)" name="min_trace_width" value={rules.min_trace_width ?? 0} onChange={handleRuleChange} />
              <RuleField label="Max trace width (mm)" name="max_trace_width" value={rules.max_trace_width ?? 0} onChange={handleRuleChange} />
              <RuleField label="Min edge clearance (mm)" name="min_edge_clearance" value={rules.min_edge_clearance ?? 0} onChange={handleRuleChange} />
              <RuleField label="Min drill spacing (mm)" name="min_drill_spacing" value={rules.min_drill_spacing ?? 0} onChange={handleRuleChange} />
              <RuleField label="Min component spacing (mm)" name="min_component_spacing" value={rules.min_component_spacing ?? 0} onChange={handleRuleChange} />
              <RuleField label="Track-edge clearance (mm)" name="min_track_edge_clearance" value={rules.min_track_edge_clearance ?? 0} onChange={handleRuleChange} />
              <RuleField label="Max board width (mm)" name="max_part_width" value={rules.max_part_width ?? 0} onChange={handleRuleChange} />
              <RuleField label="Max board height (mm)" name="max_part_height" value={rules.max_part_height ?? 0} onChange={handleRuleChange} />
              <RuleField label="Deep ERC checks" name="enable_deep_erc" value={rules.enable_deep_erc ?? false} onChange={handleRuleChange} type="checkbox" />
            </div>
          </div>

          <div className="validation-form__section">
            <div className="validation-form__header">
              <h3>Tolerances</h3>
              <p>Set the reference-comparison tolerance windows used during validation.</p>
            </div>

            <div className="validation-form__grid">
              <RuleField label="Board tolerance (mm)" name="board_tolerance" value={tolerances.board_tolerance ?? 0.1} onChange={handleToleranceChange} />
              <RuleField label="Drill position tolerance (mm)" name="drill_position_tolerance" value={tolerances.drill_position_tolerance ?? 0.25} onChange={handleToleranceChange} />
              <RuleField label="Drill diameter tolerance (mm)" name="drill_diameter_tolerance" value={tolerances.drill_diameter_tolerance ?? 0.05} onChange={handleToleranceChange} />
              <RuleField label="Component position tolerance (mm)" name="component_position_tolerance" value={tolerances.component_position_tolerance ?? 0.25} onChange={handleToleranceChange} />
              <RuleField label="Rotation tolerance (deg)" name="component_rotation_tolerance" value={tolerances.component_rotation_tolerance ?? 1} onChange={handleToleranceChange} />
            </div>

            <button className="button button--primary validation-form__submit" type="submit" disabled={submitting}>
              {submitting ? "Running validation..." : "Run Validation"}
            </button>

            {submitError ? <div className="validation-banner validation-banner--error">{submitError}</div> : null}
          </div>
        </form>

        <div className="validation-results">
          {summaryCards.length ? (
            <Reveal className="validation-results__summary validation-results__summary--popup">
              {summaryCards.map((card) => (
                <div className="validation-metric" key={card.label}>
                  <span>{card.label}</span>
                  <strong>{card.value}</strong>
                </div>
              ))}
            </Reveal>
          ) : null}

          {result ? (
            <>
              <Reveal className="validation-results__panel">
                <div className="validation-results__panel-head">
                  <div>
                    <h3>Validation Summary</h3>
                    <p>{result.reference_change_summary}</p>
                  </div>
                  <button className="button button--secondary" onClick={downloadReport}>
                    Download PDF
                  </button>
                </div>
                <div className="validation-results__stats-grid">
                  <div>
                    <span>Candidate</span>
                    <strong>{result.candidate.name}</strong>
                    <small>{result.candidate.extension}</small>
                  </div>
                  <div>
                    <span>Overall status</span>
                    <strong>{result.summary.overall_status}</strong>
                    <small>{result.summary.n_fail} fail / {result.summary.n_warn} warn / {result.summary.n_pass} pass</small>
                  </div>
                  <div>
                    <span>Reference</span>
                    <strong>{result.reference.name || "None"}</strong>
                    <small>{result.reference.metrics ? "Comparison active" : "No reference comparison"}</small>
                  </div>
                </div>
              </Reveal>

              <Reveal className="validation-results__panel">
                <h3>Measured Candidate Metrics</h3>
                <div className="validation-results__metrics-list">
                  {Object.entries(result.candidate.metrics).map(([key, value]) => (
                    <div key={key} className="validation-results__metric-row">
                      <span>{key.replaceAll("_", " ")}</span>
                      <strong>{String(value)}</strong>
                    </div>
                  ))}
                </div>
              </Reveal>

              {result.reference.metrics ? (
                <Reveal className="validation-results__panel">
                  <h3>Measured Reference Metrics</h3>
                  <div className="validation-results__metrics-list">
                    {Object.entries(result.reference.metrics).map(([key, value]) => (
                      <div key={key} className="validation-results__metric-row">
                        <span>{key.replaceAll("_", " ")}</span>
                        <strong>{String(value)}</strong>
                      </div>
                    ))}
                  </div>
                </Reveal>
              ) : null}

              <Reveal className="validation-results__panel">
                <h3>All Validation Results</h3>
                <ResultTable rows={result.results} />
              </Reveal>
            </>
          ) : null}
        </div>
      </section>
    </main>
  );
}
