import { findMagnet, isMagnet, magnetFromInput, magnetHash, magnetName } from "./magnet";

const MAGNET = "magnet:?xt=urn:btih:ABC123&dn=Some.Show.S01E01.mkv&tr=udp%3A%2F%2Ft";

describe("isMagnet", () => {
  it.each([
    [MAGNET, true],
    [`  ${MAGNET}  `, true],
    ["MAGNET:?xt=urn:btih:a", true],
    ["https://example.com", false],
    ["magnet:", false],
    ["", false],
  ])("%s -> %s", (text, expected) => {
    expect(isMagnet(text)).toBe(expected);
  });
});

describe("findMagnet", () => {
  const NAMED = "magnet:?xt=urn:btih:abc&dn=Show(2024)";
  it.each([
    [MAGNET, MAGNET],
    [`  ${MAGNET}\n`, MAGNET],
    [`grab this: ${MAGNET} thanks`, MAGNET],
    [`Title: Show\nLink:\n${MAGNET}\nSize: 1 GB`, MAGNET],
    [`<a href="${MAGNET}">link</a>`, MAGNET],
    [`${MAGNET} and magnet:?xt=urn:btih:def`, MAGNET],
    ["no links here", null],
    // Sentence and markdown punctuation around a link isn't part of it.
    [`Here it is: ${MAGNET}.`, MAGNET],
    [`Got it ${MAGNET}!`, MAGNET],
    [`(see ${MAGNET})`, MAGNET],
    [`[download](${MAGNET})`, MAGNET],
    [`[download](${MAGNET}).`, MAGNET],
    // ...but balanced brackets are.
    [`see ${NAMED}`, NAMED],
    [`[x](${NAMED})`, NAMED],
    // In running text a space ends the link, so trailing words aren't swallowed.
    [`${MAGNET} - the new episode`, MAGNET],
    ["look: magnet:?xt=urn:btih:abc&dn=Some Show", "magnet:?xt=urn:btih:abc&dn=Some"],
    // The prefix itself is never trimmed away.
    ["magnet:?.", "magnet:?."],
  ])("%j", (text, expected) => {
    expect(findMagnet(text)).toBe(expected);
  });
});

describe("magnetFromInput", () => {
  it.each([
    [MAGNET, MAGNET],
    [`  ${MAGNET}.`, MAGNET],
    // The field holds one magnet, so an unencoded name is kept whole and made URL-safe.
    ["magnet:?xt=urn:btih:abc&dn=Some Show", "magnet:?xt=urn:btih:abc&dn=Some%20Show"],
    ["magnet:?xt=urn:btih:abc&dn=A B C&tr=x", "magnet:?xt=urn:btih:abc&dn=A%20B%20C&tr=x"],
    // Anything else is searched, like a paste.
    [`try this one: ${MAGNET}.`, MAGNET],
    ["not a link", null],
    ["", null],
  ])("%j", (value, expected) => {
    expect(magnetFromInput(value)).toBe(expected);
  });
});

describe("magnetName", () => {
  it.each([
    [MAGNET, "Some.Show.S01E01.mkv"],
    ["magnet:?xt=urn:btih:a&dn=Two+Words", "Two Words"],
    ["magnet:?xt=urn:btih:a&dn=caf%C3%A9", "café"],
    ["magnet:?xt=urn:btih:a&dn=", null],
    ["magnet:?xt=urn:btih:a", null],
    ["not a magnet&dn=x", null],
  ])("%s -> %s", (magnet, expected) => {
    expect(magnetName(magnet)).toBe(expected);
  });
});

describe("magnetHash", () => {
  it.each([
    [MAGNET, "abc123"],
    ["magnet:?dn=x", null],
    ["magnet:?xt=urn:sha1:zz", null],
    ["nope", null],
  ])("%s -> %s", (magnet, expected) => {
    expect(magnetHash(magnet)).toBe(expected);
  });
});
