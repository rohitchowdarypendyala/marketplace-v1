declare module 'node:sqlite' {
  // Minimal typing shim for Node's experimental sqlite bindings.
  // We only use DatabaseSync.prepare().get/.all and exec().
  export class DatabaseSync {
    constructor(path: string);
    exec(sql: string): void;
    prepare(sql: string): {
      get: (...params: any[]) => any;
      all: (...params: any[]) => any[];
      run: (...params: any[]) => any;
    };
  }
}
