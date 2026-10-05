const MAGNET = /magnet:\?[^\s"'<>]+/i;
const PREFIX_LENGTH = "magnet:?".length;
// Punctuation that ends a sentence around a link rather than belonging to it.
const SENTENCE_END = new Set([".", ",", ";", ":", "!", "?", "*", "_", "~"]);
const OPENER: Record<string, string> = { ")": "(", "]": "[", "}": "{" };

export function isMagnet(text: string): boolean {
  return /^magnet:\?/i.test(text.trim());
}

/**
 * The first magnet link inside arbitrary pasted text, if any. In running text a space ends the
 * link: an unencoded space in a magnet's name can't be told apart from the words after it.
 */
export function findMagnet(text: string): string | null {
  const found = text.match(MAGNET)?.[0];
  return found ? trimTrailing(found) : null;
}

/**
 * The magnet in the magnet field. The field holds one magnet, so input that starts with one is
 * all magnet, unencoded spaces included (made URL-safe); anything else is searched for one.
 */
export function magnetFromInput(value: string): string | null {
  const input = value.trim();
  if (!isMagnet(input)) return findMagnet(value);
  return trimTrailing(input).replaceAll(" ", "%20");
}

/** Drops a trailing full stop, or a closing bracket with no opener (as in a markdown link). */
function trimTrailing(link: string): string {
  let end = link.length;
  while (end > PREFIX_LENGTH + 1 && isTrailingPunctuation(link.slice(0, end))) end--;
  return link.slice(0, end);
}

function isTrailingPunctuation(text: string): boolean {
  const last = text.charAt(text.length - 1);
  const opener = OPENER[last];
  if (opener === undefined) return SENTENCE_END.has(last);
  return count(text, last) > count(text, opener);
}

const count = (text: string, char: string) => text.split(char).length - 1;

function params(magnet: string): URLSearchParams {
  return new URLSearchParams(magnet.trim().replace(/^magnet:\?/i, ""));
}

/** The display name (`dn`) a magnet advertises, which is usually the torrent's name. */
export function magnetName(magnet: string): string | null {
  if (!isMagnet(magnet)) return null;
  return params(magnet).get("dn")?.trim() || null;
}

export function magnetHash(magnet: string): string | null {
  if (!isMagnet(magnet)) return null;
  const xt = params(magnet).get("xt");
  return xt?.match(/^urn:btih:(.+)$/i)?.[1]?.toLowerCase() ?? null;
}
