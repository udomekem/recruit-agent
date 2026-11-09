// Find each judgement's quote in the redacted CV text, so the page can highlight it.
// Pure text matching: the CV is never rendered as HTML (it is candidate supplied data).
// Matching ignores case and runs of whitespace, as the API's own quote check does.

export type Segment = { text: string; marks: number[] };

function loose(s: string): string {
  return s.toLowerCase().replace(/\s+/g, " ").trim();
}

/** Map positions in a whitespace-collapsed, lowercased copy back to the original text. */
function collapsed(text: string): { flat: string; index: number[] } {
  let flat = "";
  const index: number[] = [];
  let prevSpace = true; // drop leading whitespace
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (/\s/.test(ch)) {
      if (!prevSpace) {
        flat += " ";
        index.push(i);
      }
      prevSpace = true;
    } else {
      flat += ch.toLowerCase();
      index.push(i);
      prevSpace = false;
    }
  }
  return { flat, index };
}

/** Where each quote first appears: [start, end) in the original text, or null. */
export function findQuotes(text: string, quotes: (string | null)[]): ([number, number] | null)[] {
  const { flat, index } = collapsed(text);
  return quotes.map((q) => {
    const needle = loose(q ?? "");
    if (!needle) return null;
    const at = flat.indexOf(needle);
    if (at < 0) return null;
    return [index[at], index[at + needle.length - 1] + 1];
  });
}

/** Split the text into runs; each run lists the quote numbers that cover it. */
export function segments(text: string, quotes: (string | null)[]): Segment[] {
  const ranges = findQuotes(text, quotes);
  const cuts = new Set<number>([0, text.length]);
  ranges.forEach((r) => {
    if (r) {
      cuts.add(r[0]);
      cuts.add(r[1]);
    }
  });
  const points = [...cuts].sort((a, b) => a - b);
  const out: Segment[] = [];
  for (let i = 0; i < points.length - 1; i++) {
    const [a, b] = [points[i], points[i + 1]];
    if (a === b) continue;
    const marks = ranges.flatMap((r, n) => (r && r[0] <= a && b <= r[1] ? [n] : []));
    out.push({ text: text.slice(a, b), marks });
  }
  return out;
}
