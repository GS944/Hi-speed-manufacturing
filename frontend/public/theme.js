// Applies the saved light/dark theme before first paint (external file so the CSP can forbid inline scripts).
try { var t = localStorage.getItem("ot-theme"); if (t) document.documentElement.dataset.theme = t; } catch (e) {}
