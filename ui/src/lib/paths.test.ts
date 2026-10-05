import { breadcrumbs, isWithin, joinPath, normalizePath, rootOf } from "./paths";

describe("normalizePath", () => {
  it.each([
    ["/library/", "/library"],
    ["//library//tv", "/library/tv"],
    ["/", "/"],
    ["  /a  ", "/a"],
  ])("%s -> %s", (path, expected) => {
    expect(normalizePath(path)).toBe(expected);
  });
});

describe("isWithin", () => {
  it.each([
    ["/library", "/library", true],
    ["/library/tv", "/library", true],
    ["/library/tv/", "/library/", true],
    ["/libraryx", "/library", false],
    ["/etc", "/library", false],
    ["/anything", "/", true],
  ])("%s in %s -> %s", (path, root, expected) => {
    expect(isWithin(path, root)).toBe(expected);
  });
});

describe("rootOf", () => {
  it.each([
    ["/library/tv", ["/media", "/library"], "/library"],
    ["/media/a/b", ["/media", "/media/a"], "/media/a"],
    ["/etc", ["/media"], null],
    ["/x", [], null],
  ])("%s", (path, roots, expected) => {
    expect(rootOf(path, roots)).toBe(expected);
  });
});

describe("breadcrumbs", () => {
  it.each([
    ["/library", "/library", [["/library", "/library"]]],
    [
      "/library/tv/Show",
      "/library",
      [
        ["/library", "/library"],
        ["tv", "/library/tv"],
        ["Show", "/library/tv/Show"],
      ],
    ],
    [
      "/a",
      "/",
      [
        ["/", "/"],
        ["a", "/a"],
      ],
    ],
    ["/etc", "/library", []],
  ])("%s under %s", (path, root, expected) => {
    expect(breadcrumbs(path, root).map((c) => [c.name, c.path])).toEqual(expected);
  });
});

describe("joinPath", () => {
  it.each([
    ["/library", "tv", "/library/tv"],
    ["/library/", "tv", "/library/tv"],
    ["/", "tv", "/tv"],
  ])("%s + %s", (parent, name, expected) => {
    expect(joinPath(parent, name)).toBe(expected);
  });
});
