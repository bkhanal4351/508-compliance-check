// Header.jsx — The dark-blue banner that spans the top of every page.
// It shows the EPA logo on the left and the app title next to it.
// This component receives no props (data) — it is purely decorative/branding.

export default function Header() {
  return (
    // role="banner" is an accessibility landmark so screen readers know this is the page header
    <header className="app-header" role="banner">
      {/* EPA seal logo — the image lives in frontend/public/epa_logo.png.
          Vite (our build tool) serves files from /public/ at the root URL,
          so "/epa_logo.png" resolves to that file.
          alt="EPA seal" describes the image for screen reader users */}
      <img src="/epa_logo.png" alt="EPA seal" />

      {/* The main title text displayed beside the logo */}
      <h1>508 Compliance &amp; URL Checker</h1>
      {/* &amp; renders the & character safely inside HTML/JSX */}
    </header>
  )
}
