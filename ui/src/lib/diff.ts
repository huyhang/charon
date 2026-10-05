export interface Segment {
  text: string;
  changed: boolean;
}

export interface NameDiff {
  before: Segment[];
  after: Segment[];
}

/** Words and runs of digits stay whole; every other character is its own token. */
export function tokenize(text: string): string[] {
  return text.match(/[\p{L}\p{N}]+|[^\p{L}\p{N}]/gu) ?? [];
}

/** Token-level diff of two names, for highlighting what a rule changes. */
export function diffNames(before: string, after: string): NameDiff {
  const a = tokenize(before);
  const b = tokenize(after);
  const common = lcsTable(a, b);
  const result: NameDiff = { before: [], after: [] };
  let i = 0;
  let j = 0;
  while (i < a.length || j < b.length) {
    if (i < a.length && j < b.length && a[i] === b[j]) {
      push(result.before, a[i++]!, false);
      push(result.after, b[j++]!, false);
    } else if (j < b.length && (i === a.length || common[i]![j + 1]! >= common[i + 1]![j]!)) {
      push(result.after, b[j++]!, true);
    } else {
      push(result.before, a[i++]!, true);
    }
  }
  return result;
}

// common[i][j] = length of the longest common subsequence of a[i:] and b[j:].
function lcsTable(a: string[], b: string[]): number[][] {
  const table = Array.from({ length: a.length + 1 }, () => new Array<number>(b.length + 1).fill(0));
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      table[i]![j] =
        a[i] === b[j] ? table[i + 1]![j + 1]! + 1 : Math.max(table[i + 1]![j]!, table[i]![j + 1]!);
    }
  }
  return table;
}

function push(segments: Segment[], text: string, changed: boolean): void {
  const last = segments.at(-1);
  if (last && last.changed === changed) last.text += text;
  else segments.push({ text, changed });
}
