export function normalizePath(path: string): string {
  const trimmed = path.trim().replace(/\/+/g, "/");
  return trimmed.length > 1 ? trimmed.replace(/\/$/, "") : trimmed;
}

export function isWithin(path: string, root: string): boolean {
  const p = normalizePath(path);
  const r = normalizePath(root);
  return p === r || p.startsWith(r === "/" ? "/" : `${r}/`);
}

/** The root `path` lives under (the deepest one, if roots nest), or null. */
export function rootOf(path: string, roots: readonly string[]): string | null {
  return (
    roots.filter((root) => isWithin(path, root)).sort((a, b) => b.length - a.length)[0] ?? null
  );
}

export interface Crumb {
  name: string;
  path: string;
}

/** Clickable segments from `root` down to `path`. */
export function breadcrumbs(path: string, root: string): Crumb[] {
  const p = normalizePath(path);
  const r = normalizePath(root);
  if (!isWithin(p, r)) return [];
  const rest = p.slice(r.length).split("/").filter(Boolean);
  const crumbs: Crumb[] = [{ name: r, path: r }];
  let current = r;
  for (const name of rest) {
    current = current === "/" ? `/${name}` : `${current}/${name}`;
    crumbs.push({ name, path: current });
  }
  return crumbs;
}

export function joinPath(parent: string, name: string): string {
  return normalizePath(`${parent}/${name}`);
}
