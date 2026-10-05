/** A single persisted string value. Injected so tests and SSR-free code avoid globals. */
export interface ValueStore {
  get(): string | null;
  set(value: string): void;
  clear(): void;
}

export function localStore(key: string, storage: Storage = window.localStorage): ValueStore {
  return {
    get: () => storage.getItem(key),
    set: (value) => storage.setItem(key, value),
    clear: () => storage.removeItem(key),
  };
}

export function memoryStore(initial: string | null = null): ValueStore {
  let value = initial;
  return {
    get: () => value,
    set: (next) => {
      value = next;
    },
    clear: () => {
      value = null;
    },
  };
}
