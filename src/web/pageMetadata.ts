import type { Page } from "playwright";

export type PageMetadata = {
  title: string;
  language: string;
  headings: { level: number; text: string }[];
  landmarks: Record<string, number>;
  imageCount: number;
  formControlCount: number;
  linkCount: number;
  mediaCount: number;
  hasAnimations: boolean;
};

export async function getPageMetadata(page: Page): Promise<PageMetadata> {
  return page.evaluate(() => {
    const headings = Array.from(document.querySelectorAll("h1,h2,h3,h4,h5,h6")).map((heading) => ({
      level: Number(heading.tagName.slice(1)),
      text: (heading.textContent || "").trim().replace(/\s+/g, " ")
    }));
    const landmarkSelectors: Record<string, string> = {
      main: "main,[role='main']",
      navigation: "nav,[role='navigation']",
      banner: "header,[role='banner']",
      contentinfo: "footer,[role='contentinfo']",
      search: "[role='search']",
      complementary: "aside,[role='complementary']"
    };
    const landmarks = Object.fromEntries(
      Object.entries(landmarkSelectors).map(([name, selector]) => [name, document.querySelectorAll(selector).length])
    );
    const hasAnimations = Array.from(document.querySelectorAll("*")).some((element) => {
      const style = window.getComputedStyle(element);
      return style.animationName !== "none" || style.transitionDuration !== "0s";
    });
    return {
      title: document.title || "",
      language: document.documentElement.lang || "",
      headings,
      landmarks,
      imageCount: document.images.length,
      formControlCount: document.querySelectorAll("input,select,textarea,button").length,
      linkCount: document.links.length,
      mediaCount: document.querySelectorAll("audio,video").length,
      hasAnimations
    };
  });
}

export async function extractRenderedLinks(page: Page): Promise<string[]> {
  return page.evaluate(() =>
    Array.from(document.querySelectorAll<HTMLAnchorElement>("a[href]"))
      .map((anchor) => anchor.href)
      .filter(Boolean)
  );
}
