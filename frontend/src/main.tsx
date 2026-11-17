import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./index.css";

// Apply the theme before first paint to avoid a flash of the wrong palette.
const storedTheme = localStorage.getItem("ognex.theme");
const prefersDark = window.matchMedia?.("(prefers-color-scheme: dark)").matches;
const dark = storedTheme ? storedTheme === "dark" : Boolean(prefersDark);
document.documentElement.classList.toggle("dark", dark);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
);

// PWA: register the service worker so the app can be installed on a phone or
// desktop. Service workers require a secure context (HTTPS or localhost).
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => undefined);
  });
}