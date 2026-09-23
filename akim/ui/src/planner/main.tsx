import "@fontsource/golos-text/cyrillic-400.css";
import "@fontsource/golos-text/cyrillic-500.css";
import "@fontsource/golos-text/cyrillic-600.css";
import "@fontsource/golos-text/latin-400.css";
import "@fontsource/golos-text/latin-500.css";
import "@fontsource/golos-text/latin-600.css";
import React from "react";
import ReactDOM from "react-dom/client";
import { ServicesProvider } from "../services";
import Planner from "./Planner";
import "./planner.css";
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ServicesProvider>
      <Planner />
    </ServicesProvider>
  </React.StrictMode>,
);
