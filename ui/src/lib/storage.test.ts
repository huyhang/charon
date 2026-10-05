import { localStore, memoryStore, type ValueStore } from "./storage";

describe.each<[string, () => ValueStore]>([
  ["localStore", () => localStore("charon.test")],
  ["memoryStore", () => memoryStore()],
])("%s", (_, make) => {
  it("sets, gets and clears a value", () => {
    const store = make();
    expect(store.get()).toBeNull();
    store.set("abc");
    expect(store.get()).toBe("abc");
    store.clear();
    expect(store.get()).toBeNull();
  });
});
