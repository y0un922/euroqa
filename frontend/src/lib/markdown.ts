import { defaultUrlTransform } from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

export const markdownRemarkPlugins = [remarkGfm, remarkMath];
export const markdownRehypePlugins = [rehypeKatex];

const INTERNAL_MARKDOWN_PROTOCOLS = ["reference://", "citation://"] as const;

export function markdownUrlTransform(url: string): string {
  return INTERNAL_MARKDOWN_PROTOCOLS.some((prefix) => url.startsWith(prefix))
    ? url
    : defaultUrlTransform(url);
}
