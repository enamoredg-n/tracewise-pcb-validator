import { useState } from "react";
import "./Navbar.css";

export default function Navbar({
  theme,
  navLinks,
  onNavigateHome,
  onOpenValidationCenter,
  onToggleTheme,
}) {
  const [open, setOpen] = useState(false);

  return (
    <header className="navbar">
      <div className="navbar__inner">
        <button className="navbar__brand" onClick={onNavigateHome}>
          <span className="navbar__brand-mark">LocoHoco</span>
        </button>

        <nav className={`navbar__nav ${open ? "is-open" : ""}`}>
          {navLinks.map((link) => (
            <a
              key={link.href}
              href={link.disabled ? "#top" : link.href}
              className={`navbar__link ${link.disabled ? "is-disabled" : ""}`}
              onClick={(event) => {
                if (link.disabled) {
                  event.preventDefault();
                  onNavigateHome();
                }
                setOpen(false);
              }}
            >
              {link.label}
            </a>
          ))}
        </nav>

        <div className="navbar__actions">
          <button
            className={`theme-switch theme-switch--${theme}`}
            onClick={onToggleTheme}
            aria-label="Toggle theme"
          >
            <span className="theme-switch__track">
              <span className="theme-switch__thumb" />
            </span>
            <span className="theme-switch__label">{theme === "dark" ? "Dark" : "Light"}</span>
          </button>
          <button className="button button--primary" onClick={onOpenValidationCenter}>
            Login
          </button>
          <button className="navbar__menu" onClick={() => setOpen((value) => !value)}>
            <span />
            <span />
            <span />
          </button>
        </div>
      </div>
    </header>
  );
}
