import { DatabaseSync } from 'node:sqlite';
import path from 'node:path';

// IMPORTANT: schema is frozen (creators + social_profiles only). Read-only access.
const DB_PATH = process.env.MARKETPLACE_DB_PATH || path.resolve(process.cwd(), '..', 'marketplace.db');

let _db: DatabaseSync | null = null;

export function db(): DatabaseSync {
  if (_db) return _db;
  // open readwrite to allow WAL journaling pragmas; we still only run SELECTs in GET endpoints.
  const d = new DatabaseSync(DB_PATH);
  d.exec(`PRAGMA journal_mode = WAL;`);
  d.exec(`PRAGMA synchronous = NORMAL;`);
  d.exec(`PRAGMA foreign_keys = ON;`);
  _db = d;
  return d;
}
