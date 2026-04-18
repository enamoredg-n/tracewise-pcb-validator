import "./Footer.css";

export default function Footer() {
  return (
    <footer className="footer">
      <div className="footer__panel reveal is-visible">
        <div>
          <span className="section-kicker">TraceWise</span>
          <h3>AI-assisted PCB validation presented like a product, not a prototype.</h3>
        </div>
        <p>
          Real KiCad and DXF parsing, exact rule evaluation, reference-aware comparison, and a
          cleaner narrative for technical review.
        </p>
      </div>
    </footer>
  );
}
