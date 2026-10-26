import React from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./styles.css";
import { captureInvite } from "./invitation";
const invitation = captureInvite();
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App invitation={invitation} />
  </React.StrictMode>,
);
