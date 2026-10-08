// Rendered-state fingerprint of the legacy single-page app (docs/prototypes/idx-evidence-lab-user-journey.html).
// Hashes are platform independent (DOM markup, text, computed styles). They are NOT pixel or layout based, because
// fonts and geometry differ between macOS and Linux; use `capture-screenshots` locally for same-machine pixel checks.
import { createHash } from "node:crypto";
import type { Page } from "@playwright/test";

export const PAGES = [
  "dashboard",
  "screener",
  "watchlist",
  "studies",
  "research",
  "portfolio-lab",
  "market",
  "news-universe",
  "sources",
  "settings",
] as const;

export const VIEWPORTS = {
  desktop: { width: 1440, height: 900 },
  mobile: { width: 390, height: 844 },
} as const;

export interface PageFingerprint {
  dom_sha256: string;
  text_sha256: string;
  styles_sha256: string;
  nodes: number;
  failed_requests: string[];
}

const STYLE_PROPS = [
  "display", "position", "visibility", "opacity", "overflow", "z-index",
  "width", "height", "min-width", "max-width", "min-height", "max-height",
  "margin", "padding", "border", "border-radius", "box-shadow",
  "color", "background-color", "background-image", "font-family", "font-size", "font-weight", "font-style",
  "line-height", "letter-spacing", "text-align", "text-transform", "text-decoration", "white-space",
  "flex", "flex-direction", "flex-wrap", "align-items", "justify-content", "gap",
  "grid-template-columns", "grid-template-rows", "grid-column", "grid-row",
  "top", "left", "right", "bottom", "transform", "cursor", "pointer-events",
];

const sha = (text: string) => createHash("sha256").update(text).digest("hex");

/** Serialize the app root without script/style/link elements, so moving code between files does not change it. */
async function collect(page: Page) {
  return page.evaluate((props) => {
    const root = document.getElementById("idxel-journey");
    if (!root) throw new Error("#idxel-journey missing");
    const clone = root.cloneNode(true) as HTMLElement;
    clone.querySelectorAll("script,style,link").forEach((el) => el.remove());
    const originals = Array.from(root.querySelectorAll("*")).filter((el) => !el.matches("script,style,link"));
    let styles = "";
    for (const el of originals) {
      const cs = getComputedStyle(el);
      styles += el.tagName + "|" + props.map((p) => cs.getPropertyValue(p)).join("|") + "\n";
    }
    return { dom: clone.outerHTML, text: root.innerText, styles, nodes: originals.length };
  }, STYLE_PROPS);
}

export async function settle(page: Page, maxMs = 20000): Promise<void> {
  let previous = "";
  let stable = 0;
  const started = Date.now();
  while (Date.now() - started < maxMs) {
    await page.waitForTimeout(600);
    const current = sha((await collect(page)).dom);
    stable = current === previous ? stable + 1 : 0;
    previous = current;
    if (stable >= 3) return;
  }
}

export async function fingerprint(page: Page, failed: string[]): Promise<PageFingerprint> {
  await settle(page);
  const c = await collect(page);
  return {
    dom_sha256: sha(c.dom),
    text_sha256: sha(c.text),
    styles_sha256: sha(c.styles),
    nodes: c.nodes,
    failed_requests: [...new Set(failed)].sort(),
  };
}

export async function dump(page: Page): Promise<{ dom: string; text: string; styles: string }> {
  const c = await collect(page);
  return { dom: c.dom, text: c.text, styles: c.styles };
}
