/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Sober institutional palette — the register of a bank statement, not a
        // marketing page. High contrast for projector legibility (§9).
        paper: "#f3f4f5",
        surface: "#ffffff",
        ink: "#181b20", // body text — well above the AA minimum on white
        muted: "#535a64",
        faint: "#8b929c",
        rule: "#d7dbe0",
        navy: "#1f3a5f", // primary
        navydark: "#152a44",
        // Confidence semantics — always paired with a label + a structural cue,
        // never colour alone.
        ok: "#166b46",
        okbg: "#e6f1ea",
        warn: "#8a5300",
        warnbg: "#faf0dc",
        alert: "#a3271c",
        alertbg: "#f8e5e2",
      },
      fontFamily: {
        sans: [
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
      },
      fontSize: {
        // A generous base so it reads at 3 metres.
        base: ["1.0625rem", { lineHeight: "1.55" }],
      },
      boxShadow: {
        panel: "0 1px 0 rgba(0,0,0,0.04)",
      },
    },
  },
  plugins: [],
};
